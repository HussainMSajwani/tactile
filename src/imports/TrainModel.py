from functools import total_ordering
import json
import torch
import torch_geometric as pyg
from tqdm.auto import tqdm, trange  
from .TactileDataset import TactileDataset
from pathlib import Path
from numpy import pi
from pandas import DataFrame

class TrainModel():

    def __init__(
        self, 
        extraction_case_dir, 
        model,
        n_epochs = 150,
        optimizer = 'adam',
        lr = 0.001,
        loss_func = torch.nn.L1Loss(),
        transform = None
        ):

        self.extraction_case_dir = Path(extraction_case_dir)
        self.transform = transform

        self.train_data = TactileDataset(self.extraction_case_dir / 'train', transform=transform)
        self.val_data = TactileDataset(self.extraction_case_dir / 'val', transform=transform)
        self.test_data = TactileDataset(self.extraction_case_dir / 'test', transform=transform)

        self.train_loader = pyg.loader.DataLoader(self.train_data)
        self.val_loader = pyg.loader.DataLoader(self.val_data)
        self.test_loader = pyg.loader.DataLoader(self.test_data)

        self.model = model
        self.n_epochs = n_epochs


        if optimizer == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        else:
            raise NotImplementedError('use tm.optimizer = torch.optim.<optimizer>')
        
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(self.optimizer, 'min')

        self.loss_func = loss_func

        self.device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        

    def train(self):
        self.train_losses = []
        self.val_losses = []
        self.lr = []
        for epoch in trange(1, self.n_epochs + 1, desc='training', unit='epoch'):
            epoch_loss = 0
            lr = self.optimizer.param_groups[0]['lr']
            self.lr.append(lr)
            with tqdm(self.train_loader, unit="batch") as tepoch:
                for i, data in enumerate(tepoch):
                    tepoch.set_description(f"Epoch {epoch}")
                    with torch.autograd.detect_anomaly():
                        data = data.to(self.device)
                        self.optimizer.zero_grad()
                        end_point = self.model(data)

                        loss = self.loss_func(end_point[0], data.y)
                        loss.backward()
                        self.optimizer.step()
                        
                        epoch_loss += loss.detach().item()
                        tepoch.set_postfix({
                            'train_loss': epoch_loss / (i + 1), 
                            'val_loss': self.val_losses[epoch - 1] if epoch > 0 else 'na',
                            'lr': lr
                            })

                epoch_loss /= len(self.train_data)
                val_loss = self.validate()
                self.scheduler.step(val_loss)
                tepoch.set_postfix({'train_loss': epoch_loss, 'val_loss': val_loss})
            self.train_losses.append(epoch_loss)
            self.val_losses.append(val_loss)

    def validate(self):
        loss = 0
        for i, data in enumerate(self.val_loader):      
            data = data.to(self.device)
            end_point = self.model(data)

            loss += self.loss_func(end_point[0], data.y).detach().item()
        loss /= len(self.val_data)
        return loss
    
    def test(self):
        loss = 0
        for i, data in enumerate(self.train_loader):      
            data = data.to(self.device)
            end_point = self.model(data)

            loss += self.loss_func(end_point[0], data.y).detach().item()
        loss /= len(self.train_data)
        return loss

    def log(self):
        #find model name
        name = str(type(self.model)).split('.')[-1][:-2]
        path = Path('results') / name
        if not path.exists():
            path.mkdir(parents=True)

        with open(path / 'training_params.json', 'w') as f:
            params = {
                'model': name,
                'extraction_used': self.extraction_case_dir,
                'n_epochs': self.n_epochs,
                'final_val_loss_degrees': self.val_losses[-1] * 180 / pi,
                'transform': self.transform,
            }

            json.dump(params, f, indent=4)

        train_log = {
            'epoch': [i for i in range(1, self.n_epochs + 1)], 
            'train_loss': self.train_losses,
            'val_loss': self.val_losses,
            'lr': self.lr
        }

        DataFrame(train_log).to_csv(path / 'train_log.csv', index=False)
        






