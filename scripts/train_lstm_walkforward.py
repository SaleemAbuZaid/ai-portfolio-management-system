"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Project source/configuration file supporting the APEX AI Portfolio Management System.
"""
import os
import sys
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import matplotlib.pyplot as plt
import json
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Set paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT_DIR, "data", "training", "market_training_long.parquet")
MODELS_DIR = os.path.join(ROOT_DIR, "backend", "app", "services", "ai_engine", "models")
ARTIFACTS_DIR = os.path.join(ROOT_DIR, "data", "training", "artifacts")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# Device config
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Using device: {device}")

# Define the LSTM Model directly in the script for standalone training
class DeepLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=64, num_layers=2, output_size=1, dropout=0.2):
        super(DeepLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # batch_first=True means input shape is (batch, seq_len, features)
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, 
                            batch_first=True, dropout=dropout if num_layers > 1 else 0)
        
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, output_size)
        )
        
    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(device)
        
        out, _ = self.lstm(x, (h0, c0))
        # Take the output of the last time step
        out = self.fc(out[:, -1, :])
        return out

class TimeSeriesDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y)
        
    def __len__(self):
        return len(self.X)
    
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

def load_data():
    if not os.path.exists(DATA_PATH):
        print(f"Error: Dataset not found at {DATA_PATH}")
        sys.exit(1)
    
    df = pd.read_parquet(DATA_PATH)
    # Sort just in case
    if 'timestamp' in df.columns:
        df = df.sort_values(by=['symbol', 'timestamp'])
    return df

def prepare_sequences(data, target, window_size=60):
    X, y = [], []
    for i in range(len(data) - window_size):
        X.append(data[i : i + window_size])
        y.append(target[i + window_size])
    return np.array(X), np.array(y)

def train_and_evaluate_ticker(ticker, df_ticker, window_size=60, epochs=20, batch_size=64):
    print(f"\n--- Training Deep-LSTM for {ticker} ---")
    
    # We will predict future_return_5 directly (regression) or the close price
    # Let's predict the normalized close price
    if 'close' not in df_ticker.columns:
        print(f"Skipping {ticker}, no close price.")
        return None
        
    prices = df_ticker['close'].values.reshape(-1, 1)
    
    # Need enough data
    if len(prices) < window_size * 3:
        print(f"Skipping {ticker}, not enough data ({len(prices)} rows).")
        return None
        
    # Scale
    scaler = MinMaxScaler()
    scaled_prices = scaler.fit_transform(prices)
    
    X, y = prepare_sequences(scaled_prices, scaled_prices, window_size)
    
    # Train/Test Split (80/20) - Simple walk-forward for the series
    train_size = int(len(X) * 0.8)
    X_train, y_train = X[:train_size], y[:train_size]
    X_test, y_test = X[train_size:], y[train_size:]
    
    train_dataset = TimeSeriesDataset(X_train, y_train)
    test_dataset = TimeSeriesDataset(X_test, y_test)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
    
    # Initialize Model
    model = DeepLSTM(input_size=1, hidden_size=64, num_layers=2, output_size=1).to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    train_losses = []
    val_losses = []
    
    for epoch in range(epochs):
        model.train()
        epoch_train_loss = 0
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)
            
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            
            epoch_train_loss += loss.item() * batch_X.size(0)
            
        epoch_train_loss /= len(train_loader.dataset)
        train_losses.append(epoch_train_loss)
        
        # Validation
        model.eval()
        epoch_val_loss = 0
        with torch.no_grad():
            for batch_X, batch_y in test_loader:
                batch_X, batch_y = batch_X.to(device), batch_y.to(device)
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                epoch_val_loss += loss.item() * batch_X.size(0)
                
        epoch_val_loss /= len(test_loader.dataset)
        val_losses.append(epoch_val_loss)
        
        if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
            print(f"Epoch [{epoch+1}/{epochs}], Train Loss: {epoch_train_loss:.6f}, Val Loss: {epoch_val_loss:.6f}")
            
    # Evaluation
    model.eval()
    all_preds = []
    all_actuals = []
    with torch.no_grad():
        for batch_X, batch_y in test_loader:
            batch_X = batch_X.to(device)
            outputs = model(batch_X)
            all_preds.extend(outputs.cpu().numpy())
            all_actuals.extend(batch_y.numpy())
            
    # Inverse transform
    preds_inv = scaler.inverse_transform(np.array(all_preds).reshape(-1, 1))
    actuals_inv = scaler.inverse_transform(np.array(all_actuals).reshape(-1, 1))
    
    mae = mean_absolute_error(actuals_inv, preds_inv)
    rmse = np.sqrt(mean_squared_error(actuals_inv, preds_inv))
    
    # Calculate Directional Accuracy
    # Did the prediction and actual move in the same direction from previous timestep?
    # For sequence i, the previous timestep is X_test[i, -1, 0] (the last element of the input sequence)
    prev_vals = scaler.inverse_transform(X_test[:, -1, 0].reshape(-1, 1))
    
    actual_dir = np.sign(actuals_inv - prev_vals)
    pred_dir = np.sign(preds_inv - prev_vals)
    
    # Avoid 0
    actual_dir[actual_dir == 0] = 1
    pred_dir[pred_dir == 0] = 1
    
    dir_acc = np.mean(actual_dir == pred_dir)
    
    print(f"Metrics -> MAE: {mae:.4f}, RMSE: {rmse:.4f}, DirAcc: {dir_acc:.4f}")
    
    # Save Model Checkpoint
    # Format matches forecast_model.py expectations
    safe_ticker = ticker.replace("/", "_").lower()
    model_path = os.path.join(MODELS_DIR, f"forecast_{safe_ticker}.pth")
    torch.save({
        'model_state_dict': model.state_dict(),
        'min_p': scaler.data_min_[0],
        'max_p': scaler.data_max_[0],
        'window_size': window_size,
        'ticker': ticker,
        'mae': mae,
        'rmse': rmse,
        'dir_acc': dir_acc,
        'trained_at': datetime.now().isoformat()
    }, model_path)
    
    return {
        'ticker': ticker,
        'mae': mae,
        'rmse': rmse,
        'dir_acc': dir_acc,
        'train_losses': train_losses,
        'val_losses': val_losses,
        'actuals': actuals_inv[-100:].flatten().tolist(), # Keep last 100 for plotting
        'preds': preds_inv[-100:].flatten().tolist()
    }

def generate_artifacts(results_dict):
    print("\nGenerating LSTM Artifacts...")
    
    # 1. Aggregate metrics
    metrics_list = []
    for ticker, res in results_dict.items():
        metrics_list.append({
            "ticker": ticker,
            "MAE": res['mae'],
            "RMSE": res['rmse'],
            "Directional_Accuracy": res['dir_acc']
        })
        
        # Plot Loss Curve for each
        plt.figure(figsize=(8, 5))
        plt.plot(res['train_losses'], label='Train Loss')
        plt.plot(res['val_losses'], label='Val Loss')
        plt.title(f'LSTM Loss Curve: {ticker}')
        plt.xlabel('Epoch')
        plt.ylabel('MSE Loss')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        safe_ticker = ticker.replace("/", "_")
        plt.savefig(os.path.join(ARTIFACTS_DIR, f'lstm_loss_{safe_ticker}.png'))
        plt.close()
        
        # Plot Predictions vs Actual for last 100 points
        plt.figure(figsize=(10, 5))
        plt.plot(res['actuals'], label='Actual Price', color='blue')
        plt.plot(res['preds'], label='Predicted Price', color='orange', linestyle='--')
        plt.title(f'LSTM Walk-Forward Validation: {ticker}')
        plt.xlabel('Time Step (Last 100)')
        plt.ylabel('Price')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(os.path.join(ARTIFACTS_DIR, f'lstm_preds_{safe_ticker}.png'))
        plt.close()
        
    # Save master report
    avg_dir_acc = np.mean([m['Directional_Accuracy'] for m in metrics_list])
    avg_mae = np.mean([m['MAE'] for m in metrics_list])
    
    report = {
        "model": "Deep-LSTM Apex Architecture",
        "evaluation_method": "Chronological Holdout (80/20)",
        "average_directional_accuracy": float(avg_dir_acc),
        "average_mae": float(avg_mae),
        "ticker_metrics": metrics_list,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(os.path.join(ARTIFACTS_DIR, 'lstm_metrics.json'), 'w') as f:
        json.dump(report, f, indent=4)
        
    print(f"LSTM Artifacts saved to {ARTIFACTS_DIR}")

def main():
    print("=== Apex Deep-LSTM Walk-Forward Training ===")
    df = load_data()
    
    # For training speed in this environment, let's pick top assets if there are too many
    # But ideally train all
    symbols = df['symbol'].unique()
    
    results = {}
    for sym in symbols:
        df_sym = df[df['symbol'] == sym].copy()
        res = train_and_evaluate_ticker(sym, df_sym, epochs=15) # Keep epochs reasonable for full dataset
        if res:
            results[sym] = res
            
    if results:
        generate_artifacts(results)
    
    print("=== LSTM Training Complete ===")

if __name__ == "__main__":
    main()
