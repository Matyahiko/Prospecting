import pandas as pd
import numpy as np
import os
import time
from sklearn.metrics import mean_squared_error
from catboost import CatBoostRegressor
import torch
from torch.utils.data import DataLoader,Dataset
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import optuna
import h5py
from joblib import Memory

GREEN = '\033[32m'
YELLOW = '\033[33m'
RESET = '\033[0m'


cache_dir = './cache/crypto'
memory = Memory(cache_dir, verbose=0)

#@memory.cache
class ParallelFeaturesTimeSeriesDataset(Dataset):
    def __init__(self, data, sequence_length, num_features):
        # Separate target from features
        self.features = torch.FloatTensor(data.drop('target', axis=1).values)
        self.targets = torch.FloatTensor(data['target'].values)
        self.sequence_length = sequence_length
        self.num_features = num_features - 1  # Subtract 1 for the target column

    def __len__(self):
        return len(self.features) - self.sequence_length + 1

    def __getitem__(self, index):
        feature_sequence = self.features[index:index + self.sequence_length]
        # Reshape the feature sequence
        feature_sequence = feature_sequence.transpose(0, 1).reshape(-1)
        
        # Get the corresponding target (use the last value in the sequence)
        # Reshape the sequence to [f1_1, f2_1, ..., f1_2, f2_2, ..., f1_n, f2_n, ...]   
        target = self.targets[index + self.sequence_length - 1]

        return feature_sequence, target

#@memory.cache
def data_loader(train_df, val_df, test_df, sequence_length, num_features, batch_size):
    train_dataset = ParallelFeaturesTimeSeriesDataset(train_df, sequence_length, num_features)
    val_dataset = ParallelFeaturesTimeSeriesDataset(val_df, sequence_length, num_features)
    test_dataset = ParallelFeaturesTimeSeriesDataset(test_df, sequence_length, num_features)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    return train_loader, val_loader, test_loader

def get_full_data(data_loader):
    full_data = []
    full_labels = []
    for batch in data_loader:
        features, labels = batch
        full_data.append(features)
        full_labels.append(labels)
    return torch.cat(full_data, dim=0).numpy(), torch.cat(full_labels, dim=0).numpy()

#@memory.cache
def load_data_from_hdf5(filename):
    
   with h5py.File(f"crypto/processed/{filename}.h5", 'r') as hf:
        # 文字列のリストとして読み込む
        columns = list(hf.attrs['columns'])
        
        train_data = {col: hf['train'][col][:] for col in columns}
        val_data = {col: hf['val'][col][:] for col in columns}
        test_data = {col: hf['test'][col][:] for col in columns}
        
        train_df = pd.DataFrame(train_data)
        val_df = pd.DataFrame(val_data)
        test_df = pd.DataFrame(test_data)
    
   return train_df, val_df, test_df


def objective(trial):
    # 全データの取得
    train_data, train_labels = get_full_data(train_loader)
    val_data, val_labels = get_full_data(val_loader)
    
    # print(GREEN + f"Train data shape: {train_data.shape }" +"\n" + RESET)
    # print(GREEN + f"Train labels shape: {train_labels.shape}" +"\n" + RESET)
    # print(GREEN + f"Val data shape: {val_data.shape}" +"\n" + RESET)
    # print(GREEN + f"Val labels shape: {val_labels.shape}" +"\n" + RESET)
    # print("Train data type:", train_data.dtype)
    # print("Train labels type:", train_labels.dtype)
    # print("Train data range:", train_data.min(), "-", train_data.max())
    # print("Train labels range:", train_labels.min(), "-", train_labels.max())
    # print("Infinite values in train data:", np.isinf(train_data).any())
    # print("NaN values in train data:", np.isnan(train_data).any())
    # print("Infinite values in train labels:", np.isinf(train_labels).any())
    # print("NaN values in train labels:", np.isnan(train_labels).any())
    

    # Optunaによるパラメータ探索
   # ハイパーパラメータの定義
    params = {
        "iterations": trial.suggest_int("iterations", 100, 1000),
        "learning_rate": trial.suggest_loguniform("learning_rate", 1e-3, 1.0),
        "depth": trial.suggest_int("depth", 4, 10),
        "l2_leaf_reg": trial.suggest_loguniform("l2_leaf_reg", 1e-8, 100.0),
        "bootstrap_type": trial.suggest_categorical("bootstrap_type", ["Bayesian", "Bernoulli", "MVS"]),
        "random_strength": trial.suggest_uniform("random_strength", 1e-9, 10),
        #"bagging_temperature": trial.suggest_loguniform("bagging_temperature", 0.01, 100.0),
        "loss_function": "RMSE"  # 明示的に損失関数を指定
    }
    
    # モデルの学習
    model = CatBoostRegressor(**params)
    model.fit(train_data, 
            train_labels, 
            eval_set=(val_data, val_labels), 
            early_stopping_rounds=20, 
            verbose=False)

    # 検証データでの予測
    preds = model.predict(val_data)

    # 評価指標の計算（ここではRMSEを使用）
    rmse = np.sqrt(mean_squared_error(val_labels, preds))

    return -rmse  # 最小化問題を最大化問題に変換


filename = "BTC-JPY_15min_2021-2024"
train_df, val_df, test_df = load_data_from_hdf5(filename)

sequence_length = 12
num_features = len(train_df.columns)-1
batch_size = 20

train_loader, val_loader, test_loader = data_loader(
    train_df, 
    val_df, 
    test_df,
    sequence_length,
    num_features,
    batch_size
)

#debug
if True:
    print(f"num_features : {num_features}")
        # データローダーからイテレータを取得
    loader_iter = iter(train_loader)
    print(f"DataLoader Info:")
    print(f"Batch size: {test_loader.batch_size}")
    print(f"Number of batches: {len(test_loader)}")
    first_batch = next(loader_iter)
    features, labels = first_batch
    print(f"\nFirst batch shape: {features.shape}")
    print(f"Data type: {features.dtype}")
    # サンプルデータの表示
    print("\nSample data (first 5 elements of first item in batch):")
    print(features[0, :5])
    print("label")
    print(labels)

# Optunaによる最適化の実行
study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=100)

# 最良のトライアルの表示
print("Best trial:")
trial = study.best_trial
print("  Value: ", -trial.value)  # RMSEの値（元の最小化問題の値）
print("  Params: ")
for key, value in trial.params.items():
    print(f"    {key}: {value}")

# 最適化されたパラメータでモデルを再学習
best_params = trial.params
best_model = CatBoostRegressor(**best_params)
train_data, train_labels = get_full_data(train_loader)
best_model.fit(train_data, train_labels)

# モデルの保存
best_model.save_model("crypto/models/best_catboost_model.cbm")

# 特徴量の寄与率を計算
feature_importance = best_model.get_feature_importance()
feature_names = best_model.feature_names_

# 特徴量の寄与率を降順にソート
sorted_idx = np.argsort(feature_importance)
sorted_features = [feature_names[i] for i in sorted_idx]
sorted_importance = feature_importance[sorted_idx]

# 上位20個の特徴量の寄与率をプロット
plt.figure(figsize=(10, 8))
plt.barh(range(20), sorted_importance[-20:])
plt.yticks(range(20), sorted_features[-20:])
plt.xlabel('Feature Importance')
plt.title('Top 20 Most Important Features')
plt.tight_layout()
plt.savefig('crypto/fig/feature_importance.png')
plt.close()

# 特徴量の寄与率を表示
print("\nFeature Importance:")
for feature, importance in zip(sorted_features[-20:], sorted_importance[-20:]):
    print(f"{feature}: {importance:.4f}")
    