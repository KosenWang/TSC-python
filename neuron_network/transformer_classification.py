import numpy as np
import torch
from torch import nn, optim, Tensor
import torch.utils.data as Data
from typing import Tuple
import os
import sys
import json
sys.path.append('../')
import utils.csv as csv
from models.transformer import TransformerClassifier
import utils.validation as val
import utils.plot as plot


# file path
PATH='D:\\Deutschland\\FUB\\master_thesis\\data'
DATA_DIR = os.path.join(PATH, 'gee', 'output', 'daily_padding')
LABEL_CSV = 'label_pure.csv'
METHOD = 'classification'
MODEL = 'transformer'
UID = '5pure'
MODEL_NAME = MODEL + '_' + UID
LABEL_PATH = os.path.join(PATH, 'ref', 'part', LABEL_CSV)
MODEL_PATH = f'../outputs/models/{METHOD}/{MODEL_NAME}.pth'

# general hyperparameters
BATCH_SIZE = 64
LR = 0.01
EPOCH = 2
SEED = 24

# hyperparameters for Transformer model
num_bands = 10
num_classes = 8
d_model = 16
nhead = 4
num_layers = 1
dim_feedforward = 32


def save_hyperparameters() -> None:
    """Save hyperparameters into a json file"""
    params = {
        'general hyperparameters': {
            'batch size': BATCH_SIZE,
            'learning rate': LR, 
            'epoch': EPOCH,
            'seed': SEED
        },
        f'{MODEL} hyperparameters': {
            'number of bands': num_bands,
            'embedding size': d_model,
            'number of heads': nhead,
            'number of layers': num_layers,
            'feedforward dimension': dim_feedforward,
            'number of classes': num_classes
        }
    }
    out_path = f'../outputs/models/{METHOD}/{MODEL_NAME}_params.json'
    with open(out_path, 'w') as f:
        data = json.dumps(params, indent=4)
        f.write(data)
    print('saved hyperparameters')


def setup_seed(seed:int) -> None:
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)


def numpy_to_tensor(x_data:np.ndarray, y_data:np.ndarray) -> Tuple[Tensor, Tensor]:
    """Transfer numpy.ndarray to torch.tensor, and necessary pre-processing like embedding or reshape"""
    # reduce dimention from (n, 1) to (n, )
    x_set = torch.from_numpy(x_data)
    y_set = torch.from_numpy(y_data)
    # standardization
    sz, seq = x_set.size(0), x_set.size(1)
    x_set = x_set.view(-1, num_bands)
    batch_norm = nn.BatchNorm1d(num_bands)
    x_set:Tensor = batch_norm(x_set)
    x_set = x_set.view(sz, seq, num_bands).detach()
    return x_set, y_set


def build_dataloader(x_set:Tensor, y_set:Tensor, batch_size:int) -> Tuple[Data.DataLoader, Data.DataLoader, Data.DataLoader]:
    """Build and split dataset, and generate dataloader for training and validation"""
    # manually split dataset
    # *******************change number here*******************
    x_train = x_set[:1105]
    y_train = y_set[:1105]
    x_val = x_set[1105:]
    y_val = y_set[1105:]
    x_test = x_set[1105:]
    y_test = y_set[1105:]
    # ******************************************************
    train_dataset = Data.TensorDataset(x_train, y_train)
    val_dataset = Data.TensorDataset(x_val, y_val)
    test_dataset = Data.TensorDataset(x_test, y_test)
    # data_loader
    train_loader = Data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4)
    val_loader = Data.DataLoader(val_dataset, batch_size=batch_size, shuffle=True, num_workers=4)
    test_loader = Data.DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=4)
    return train_loader, val_loader, test_loader


def train(model:nn.Module, epoch:int) -> Tuple[float, float]:
    model.train()
    good_pred = 0
    total = 0
    losses = []
    for i, (inputs, refs) in enumerate(train_loader):
        # exchange dimension 0 and 1 of inputs depending on batch_first or not
        inputs:Tensor = inputs.transpose(0, 1)
        labels:Tensor = refs[:,1]
        # put the data in gpu
        inputs = inputs.to(device)
        labels = labels.to(device)
        # forward pass
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        # recording training accuracy
        outputs = softmax(outputs)
        good_pred += val.true_pred_num(labels, outputs)
        total += labels.size(0)
        # record training loss
        losses.append(loss.item())
        # backward and optimize
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    # average train loss and accuracy for one epoch
    acc = good_pred / total
    train_loss = np.average(losses)
    print('Epoch[{}/{}] | Train Loss: {:.4f} | Train Accuracy: {:.2f}% '
        .format(epoch+1, EPOCH, train_loss, acc * 100), end="")
    return train_loss, acc


def validate(model:nn.Module) -> Tuple[float, float]:
    model.eval()
    with torch.no_grad():
        good_pred = 0
        total = 0
        losses = []
        for (inputs, refs) in val_loader:
            # exchange dimension 0 and 1 of inputs depending on batch_first or not
            inputs:Tensor = inputs.transpose(0, 1)
            labels:Tensor = refs[:,1]
            # put the data in gpu
            inputs = inputs.to(device)
            labels = labels.to(device)
            # prediction
            outputs:Tensor = model(inputs)
            loss = criterion(outputs, labels)
            # recording validation accuracy
            outputs = softmax(outputs)
            good_pred += val.true_pred_num(labels, outputs)
            total += labels.size(0)
            # record validation loss
            losses.append(loss.item())
        # average train loss and accuracy for one epoch
        acc = good_pred / total
        val_loss = np.average(losses)
    print('| Validation Loss: {:.4f} | Validation Accuracy: {:.2f}%'
        .format(val_loss, 100 * acc))
    return val_loss, acc


def test(model:nn.Module) -> None:
    """Test best model"""
    model.eval()
    with torch.no_grad():
        y_true = []
        y_pred = []
        for (inputs, refs) in test_loader:
            # exchange dimension 0 and 1 of inputs depending on batch_first or not
            inputs:Tensor = inputs.transpose(0, 1)
            labels:Tensor = refs[:,1]
            # put the data in gpu
            inputs = inputs.to(device)
            labels = labels.to(device)
            # prediction
            outputs:Tensor = model(inputs)
            outputs = softmax(outputs)
            _, predicted = torch.max(outputs.data, 1)
            y_true += refs.tolist()
            refs[:, 1] = predicted
            y_pred += refs.tolist()
        # *************************change class here*************************
        classes = ['Spruce','Douglas Fir','Pine','Oak','Beech']
        # *******************************************************************
        ref = csv.list_to_dataframe(y_true, ['id', 'class'], False)
        pred = csv.list_to_dataframe(y_pred, ['id', 'class'], False)
        csv.export(ref, f'../outputs/csv/{METHOD}/{MODEL_NAME}_ref.csv', True)
        csv.export(pred, f'../outputs/csv/{METHOD}/{MODEL_NAME}_pred.csv', True)
        plot.draw_confusion_matrix(ref, pred, classes, MODEL_NAME)



if __name__ == "__main__":
    # set random seed
    setup_seed(SEED)
    # Device configuration
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    # dataset
    x_data, y_data = csv.to_numpy(DATA_DIR, LABEL_PATH)
    x_set, y_set = numpy_to_tensor(x_data, y_data)
    train_loader, val_loader, test_loader = build_dataloader(x_set, y_set, BATCH_SIZE)
    # model
    model = TransformerClassifier(num_bands, num_classes, d_model, nhead, num_layers, dim_feedforward).to(device)
    save_hyperparameters()
    # loss and optimizer
    # ******************change number of samples here******************
    # samples = torch.tensor([24106/5, 751, 3413, 1345, 2019, 1199, 8010/2, 964])
    # weight = 1 / samples
    # *****************************************************************
    criterion = nn.CrossEntropyLoss().to(device)
    optimizer = optim.Adam(model.parameters(), LR)
    softmax = nn.Softmax(dim=1).to(device)
    # evaluate terms
    train_epoch_loss = []
    val_epoch_loss = []
    train_epoch_acc = []
    val_epoch_acc = []
    max_val_acc = 0
    # train and validate model
    print("start training")
    for epoch in range(EPOCH):
        train_loss, train_acc = train(model, epoch)
        val_loss, val_acc = validate(model)
        if val_acc > max_val_acc:
            torch.save(model.state_dict(), MODEL_PATH)
            max_val_acc = val_acc
        # record loss and accuracy
        train_epoch_loss.append(train_loss)
        train_epoch_acc.append(train_acc)
        val_epoch_loss.append(val_loss)
        val_epoch_acc.append(val_acc)
    # visualize loss and accuracy during training and validation
    plot.draw_curve(train_epoch_loss, val_epoch_loss, 'loss', METHOD, MODEL_NAME)
    plot.draw_curve(train_epoch_acc, val_epoch_acc, 'accuracy', METHOD, MODEL_NAME)
    # test best model
    print('start testing')
    model.load_state_dict(torch.load(MODEL_PATH))
    test(model)
    print('plot result successfully')