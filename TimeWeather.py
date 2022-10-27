import glob
import json
import warnings
import numpy as np
import paddle
import paddle.vision.transforms as T
import pandas as pd
from PIL import Image
from paddle.io import DataLoader, Dataset
from paddle.vision.models import resnet18

warnings.filterwarnings("ignore")

# 根据head标注提取所需要的信息，如训练集文件名和天气时间信息
train_json = pd.read_json('D:/TimeAndWeather/train_dataset/train.json')
train_json['filename'] = train_json['annotations'].apply(lambda x: x['filename'].replace('\\', '/'))
train_json['period'] = train_json['annotations'].apply(lambda x: x['period'])
train_json['weather'] = train_json['annotations'].apply(lambda x: x['weather'])

train_json.head()

# 将标签进行编码
train_json['period'], period_dict = pd.factorize(train_json['period'])
train_json['weather'], weather_dict = pd.factorize(train_json['weather'])

train_json['period'].value_counts()

train_json['weather'].value_counts()


# 自定义数据集
class WeatherDataset(Dataset):
    def __init__(self, df):
        super(WeatherDataset, self).__init__()
        self.df = df

        self.transform = T.Compose([
            T.Resize(size=(340, 340)),
            T.RandomCrop(size=(256, 256)),
            T.RandomRotation(10),
            T.RandomHorizontalFlip(),
            T.RandomVerticalFlip(),
            T.ToTensor(),
            T.Normalize(mean=0.5, std=0.5)
        ])

    # 对数据集进行数据增强
    def __getitem__(self, index):
        file_name = self.df['filename'].iloc[index]
        img = Image.open(file_name)
        img = self.transform(img)
        return img, \
               paddle.to_tensor(self.df['period'].iloc[index]), \
               paddle.to_tensor(self.df['weather'].iloc[index])

    def __len__(self):
        return len(self.df)


# 训练集
train_dataset = WeatherDataset(train_json.iloc[:-400])
train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)
# 验证集
val_dataset = WeatherDataset(train_json.iloc[-400:])
val_loader = DataLoader(val_dataset, batch_size=64, shuffle=True)


# 自定义模型
class WeatherModel(paddle.nn.Layer):
    def __init__(self):
        super(WeatherModel, self).__init__()
        backbone = resnet18(pretrained=True)
        backbone.fc = paddle.nn.Identity()
        self.backbone = backbone

        # 分类一
        self.fc1 = paddle.nn.Linear(512, 4)
        # 分类二
        self.fc2 = paddle.nn.Linear(512, 3)

    def forward(self, x):
        out = self.backbone(x)
        logits1 = self.fc1(out)
        logits2 = self.fc2(out)
        return logits1, logits2


model = WeatherModel()
model(paddle.to_tensor(np.random.rand(10, 3, 256, 256).astype(np.float32)))

# 定义损失函数和优化器
optimizer = paddle.optimizer.Adam(parameters=model.parameters(), learning_rate=0.0001)
criterion = paddle.nn.CrossEntropyLoss()

for epoch in range(0, 1):
    Train_Loss, Val_Loss = [], []
    Train_ACC1, Train_ACC2 = [], []
    Val_ACC1, Val_ACC2 = [], []

    # 开始训练模型
    model.train()
    for i, (x, y1, y2) in enumerate(train_loader):
        pred1, pred2 = model(x)

        # 类别一二loss之和
        loss = criterion(pred1, y1) + criterion(pred2, y2)
        Train_Loss.append(loss.item())
        loss.backward()
        optimizer.step()
        optimizer.clear_grad()

        Train_ACC1.append((pred1.argmax(1) == y1.flatten()).numpy().mean())
        Train_ACC2.append((pred2.argmax(1) == y2.flatten()).numpy().mean())
    # 模型验证
    model.eval()
    for i, (x, y1, y2) in enumerate(val_loader):
        pred1, pred2 = model(x)
        loss = criterion(pred1, y1) + criterion(pred2, y2)
        Val_Loss.append(loss.item())
        Val_ACC1.append((pred1.argmax(1) == y1.flatten()).numpy().mean())
        Val_ACC2.append((pred2.argmax(1) == y2.flatten()).numpy().mean())

    if epoch % 1 == 0:
        print(f'\nEpoch: {epoch}')
        print(f'Loss {np.mean(Train_Loss):3.5f}/{np.mean(Val_Loss):3.5f}')
        print(f'period.ACC {np.mean(Train_ACC1):3.5f}/{np.mean(Val_ACC1):3.5f}')
        print(f'weather.ACC {np.mean(Train_ACC2):3.5f}/{np.mean(Val_ACC2):3.5f}')

test_df = pd.DataFrame({'filename': glob.glob('D:/TimeAndWeather/test_dataset/test_images/*.jpg')})
print(test_df)
test_df['period'] = 0
test_df['weather'] = 0
test_df = test_df.sort_values(by='filename')

test_dataset = WeatherDataset(test_df)
test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)

model.eval()
period_pred = []
weather_pred = []
# 测试集开始预测
for i, (x, y1, y2) in enumerate(test_loader):
    pred1, pred2 = model(x)
    period_pred += period_dict[pred1.argmax(1).numpy()].tolist()
    weather_pred += weather_dict[pred2.argmax(1).numpy()].tolist()

test_df['period'] = period_pred
test_df['weather'] = weather_pred

submit_json = {
    'annotations': []
}
# 导出生成结果
for row in test_df.iterrows():
    submit_json['annotations'].append({
        'filename': 'D:/TimeAndWeather/test_dataset/test_images/' + row[1].filename.split('/')[-1],
        'period': row[1].period,
        'weather': row[1].weather,
    })

with open('submit.json', 'w') as up:
    json.dump(submit_json, up)
