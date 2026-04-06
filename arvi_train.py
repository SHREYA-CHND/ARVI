# ======================================
# ARVI - REALISTIC MUSIC MOOD TRAINING
# ======================================

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report
import joblib

# -----------------------------
# STEP 1: LOAD DATA
# -----------------------------
data = pd.read_csv("data/spotify.csv")

print("Dataset Loaded\n")

# -----------------------------
# STEP 2: CREATE MOOD LABEL
# (using valence ONLY for labeling)
# -----------------------------
def mood_label(valence):
    if valence > 0.65:
        return "Happy"
    elif valence > 0.35:
        return "Calm"
    else:
        return "Sad"

data["mood"] = data["valence"].apply(mood_label)

# -----------------------------
# STEP 3: SELECT FEATURES
# (REMOVE valence to avoid cheating)
# -----------------------------
features = [
    'danceability',
    'energy',
    'loudness',
    'speechiness',
    'acousticness',
    'instrumentalness',
    'tempo'
]

X = data[features]
y = data["mood"]

# -----------------------------
# STEP 4: ENCODE LABELS
# -----------------------------
encoder = LabelEncoder()
y_encoded = encoder.fit_transform(y)

# -----------------------------
# STEP 5: SPLIT DATA
# -----------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y_encoded,
    test_size=0.2,
    random_state=42
)

# -----------------------------
# STEP 6: TRAIN MODEL
# -----------------------------
model = RandomForestClassifier(n_estimators=150)
model.fit(X_train, y_train)

# -----------------------------
# STEP 7: EVALUATE
# -----------------------------
predictions = model.predict(X_test)

accuracy = accuracy_score(y_test, predictions)

print("Model Accuracy:", accuracy)
print("\nDetailed Report:\n")
print(classification_report(y_test, predictions))

# -----------------------------
# STEP 8: SAVE MODEL
# -----------------------------
joblib.dump(model, "arvi_model.pkl")
joblib.dump(encoder, "label_encoder.pkl")

print("\n✅ Realistic ARVI model saved!")