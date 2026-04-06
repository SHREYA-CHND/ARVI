# ======================================
# ARVI - MUSIC MOOD PREDICTION
# ======================================

import joblib
import pandas as pd

# -----------------------------
# STEP 1: LOAD MODEL
# -----------------------------
model = joblib.load("arvi_model.pkl")
encoder = joblib.load("label_encoder.pkl")

print("🧠 ARVI Model Loaded Successfully\n")

# -----------------------------
# STEP 2: TAKE USER INPUT
# -----------------------------
print("Enter song audio features (values between 0 and 1 where applicable)\n")

danceability = float(input("Danceability (0–1): "))
energy = float(input("Energy (0–1): "))
loudness = float(input("Loudness (-60 to 0): "))
speechiness = float(input("Speechiness (0–1): "))
acousticness = float(input("Acousticness (0–1): "))
instrumentalness = float(input("Instrumentalness (0–1): "))
valence = float(input("Valence (0–1): "))
tempo = float(input("Tempo (BPM): "))

# -----------------------------
# STEP 3: CREATE INPUT DATAFRAME
# -----------------------------
features = pd.DataFrame([[
    danceability,
    energy,
    loudness,
    speechiness,
    acousticness,
    instrumentalness,
    valence,
    tempo
]], columns=[
    'danceability',
    'energy',
    'loudness',
    'speechiness',
    'acousticness',
    'instrumentalness',
    'valence',
    'tempo'
])

# -----------------------------
# STEP 4: PREDICT
# -----------------------------
prediction = model.predict(features)
mood = encoder.inverse_transform(prediction)

# -----------------------------
# STEP 5: RESULT
# -----------------------------
print("\n🎵 ARVI Mood Prediction:")
print("------------------------")
print("Predicted Mood:", mood[0])