import os
import datetime
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
import storage

class AdherencePredictor:
    """Predictive ML classifier that forecasts adherence risk based on historical log patterns."""
    
    def __init__(self):
        self.model = None
        self.vectorizer = TfidfVectorizer(max_features=50)
        self.is_trained = False
        
    def _extract_historical_features(self, logs: list) -> tuple[np.ndarray, np.ndarray]:
        """Convert a list of raw log entries into numerical feature arrays and targets."""
        X_rows = []
        y_rows = []
        
        # Sort logs chronologically to compute rolling miss rates accurately
        logs = sorted(logs, key=lambda l: l.get("timestamp", ""))
        
        # Track patient-medication history states to compute lag features
        history = {}  # (patient, medication) -> list of logs
        
        for i, log in enumerate(logs):
            patient = log.get("patient", "")
            med = log.get("medication", "")
            key = (patient, med)
            
            if key not in history:
                history[key] = []
            
            # Compute rolling miss rate over the last 14 days
            current_time = datetime.datetime.fromisoformat(log.get("timestamp", datetime.datetime.now().isoformat()))
            two_weeks_ago = current_time - datetime.timedelta(days=14)
            recent_logs = [l for l in history[key] if datetime.datetime.fromisoformat(l.get("timestamp", "")) >= two_weeks_ago]
            
            miss_count = sum(1 for l in recent_logs if l.get("outcome") not in ["TAKEN", "TAKEN_EARLIER"])
            miss_rate = miss_count / len(recent_logs) if recent_logs else 0.15
            
            # Outcome sequence last 3 runs (1 = success, 0 = missed/refused/no_response)
            last_runs = history[key][-3:]
            run_successes = [1 if r.get("outcome") in ["TAKEN", "TAKEN_EARLIER"] else 0 for r in last_runs]
            while len(run_successes) < 3:
                run_successes.insert(0, 1)  # Pad with success baseline
                
            # Parse scheduled time
            sched_time_str = log.get("scheduled_time", "12:00")
            try:
                dt_sched = datetime.datetime.strptime(sched_time_str, "%H:%M")
                hour = dt_sched.hour + dt_sched.minute / 60.0
            except ValueError:
                hour = 12.0
                
            # Day of week
            day_of_week = current_time.weekday()
            
            # Coherence and Latency
            latency = log.get("response_latency_sec")
            if latency is None:
                latency = 4.0
                
            coherence = log.get("coherence_score")
            if coherence is None:
                coherence = 0.85
                
            # Build feature vector
            # Features: [hour, day_of_week, miss_rate, last_run1, last_run2, last_run3, latency, coherence]
            features = [
                hour,
                float(day_of_week),
                float(miss_rate),
                float(run_successes[0]),
                float(run_successes[1]),
                float(run_successes[2]),
                float(latency),
                float(coherence)
            ]
            
            X_rows.append(features)
            
            # Target: 1 if patient missed (REFUSED, NO_RESPONSE, etc.), 0 if TAKEN/TAKEN_EARLIER
            outcome = log.get("outcome", "UNKNOWN")
            is_missed = 1 if outcome not in ["TAKEN", "TAKEN_EARLIER"] else 0
            y_rows.append(is_missed)
            
            # Update history cache
            history[key].append(log)
            
        return np.array(X_rows), np.array(y_rows)
        
    def train(self):
        """Train the classifier on persistent logs data."""
        logs = storage.load_logs()
        if not logs or len(logs) < 10:
            # Insufficient logs to train a reliable model
            self.is_trained = False
            return
            
        try:
            X, y = self._extract_historical_features(logs)
            
            # Check class distribution. Need both positive (adherent) and negative (non-adherent) classes to train
            classes = np.unique(y)
            if len(classes) < 2:
                self.is_trained = False
                return
                
            self.model = RandomForestClassifier(n_estimators=30, max_depth=4, random_state=42)
            self.model.fit(X, y)
            self.is_trained = True
            print("[AdherencePredictor] ML Model trained successfully on historical logs.")
        except Exception as e:
            print(f"[AdherencePredictor] Failed to train ML model: {e}. Falling back to heuristics.")
            self.is_trained = False
            
    def predict_risk(self, reminder: dict) -> float:
        """
        Calculate the adherence risk (0.0 to 1.0 probability of missing dose).
        If the ML model is trained, it uses Random Forest predictions.
        Otherwise, falls back to a robust clinical heuristic matrix.
        """
        logs = storage.load_logs()
        patient = reminder.get("patient", "")
        med = reminder.get("medication", "")
        time_str = reminder.get("next_run", "12:00")
        
        # Calculate current feature stats
        # Parse scheduled hour
        try:
            dt_sched = datetime.datetime.strptime(time_str, "%H:%M")
            hour = dt_sched.hour + dt_sched.minute / 60.0
        except ValueError:
            hour = 12.0
            
        # Get current day of week
        now = datetime.datetime.now()
        day_of_week = now.weekday()
        
        # Get history of logs for this patient and med
        history = [l for l in logs if l.get("patient") == patient and l.get("medication") == med]
        history = sorted(history, key=lambda l: l.get("timestamp", ""))
        
        # 14-day rolling miss rate
        two_weeks_ago = now - datetime.timedelta(days=14)
        recent_logs = [l for l in history if datetime.datetime.fromisoformat(l.get("timestamp", "")) >= two_weeks_ago]
        miss_count = sum(1 for l in recent_logs if l.get("outcome") not in ["TAKEN", "TAKEN_EARLIER"])
        miss_rate = miss_count / len(recent_logs) if recent_logs else 0.15
        
        # Last 3 runs successes
        last_runs = history[-3:]
        run_successes = [1 if r.get("outcome") in ["TAKEN", "TAKEN_EARLIER"] else 0 for r in last_runs]
        while len(run_successes) < 3:
            run_successes.insert(0, 1)
            
        # Last run stats
        last_log = history[-1] if history else {}
        last_latency = last_log.get("response_latency_sec")
        if last_latency is None:
            last_latency = 4.0
            
        last_coherence = last_log.get("coherence_score")
        if last_coherence is None:
            last_coherence = 0.85
        
        # Fallback Heuristic Risk Calculation (if model not trained)
        if not self.is_trained or self.model is None:
            # Baseline risk
            risk = 0.15
            
            # Factor 1: Miss rate increases risk
            if miss_rate > 0.4:
                risk += 0.35
            elif miss_rate > 0.2:
                risk += 0.15
                
            # Factor 2: Consecutive failures
            success_count = sum(run_successes)
            if success_count == 0:    # 3 missed doses in a row
                risk += 0.45
            elif success_count == 1:  # 2 missed doses
                risk += 0.25
            elif success_count == 2:  # 1 missed dose
                risk += 0.10
                
            # Factor 3: Last log latency and coherence indicators
            if last_latency > 8.0:
                risk += 0.15  # Slow response indicates potential confusion/distraction
            if last_coherence < 0.6:
                risk += 0.20  # Low coherence score indicates disorientation
                
            # Factor 4: Temporal vulnerability (very early or late hours)
            if hour < 7.0 or hour > 21.0:
                risk += 0.10
                
            # Cap the score safely
            return max(0.05, min(0.95, risk))
            
        # Machine Learning Random Forest Prediction
        try:
            features = [[
                hour,
                float(day_of_week),
                float(miss_rate),
                float(run_successes[0]),
                float(run_successes[1]),
                float(run_successes[2]),
                float(last_latency),
                float(last_coherence)
            ]]
            
            # Predict probability of class 1 (missed)
            prob_missed = self.model.predict_proba(features)[0][1]
            return float(prob_missed)
        except Exception as e:
            print(f"[AdherencePredictor] Prediction failure: {e}. Defaulting to baseline 0.15.")
            return 0.15


class CognitiveTracker:
    """Extracts, maps, and analyzes patient cognitive performance metrics over time."""
    
    @staticmethod
    def get_trend(patient_name: str, days: int = 30) -> dict:
        """
        Compile 30-day historical cognitive trend variables for a specific patient.
        Returns coordinates and outcome values for charting on the caregiver dashboard.
        """
        logs = storage.load_logs()
        
        # Filter logs for the specific patient and sorted chronologically
        patient_logs = [l for l in logs if l.get("patient", "").lower() == patient_name.lower()]
        patient_logs = sorted(patient_logs, key=lambda l: l.get("timestamp", ""))
        
        # Select within specified days timeframe
        now = datetime.datetime.now()
        cutoff_date = now - datetime.timedelta(days=days)
        recent_logs = [
            l for l in patient_logs 
            if datetime.datetime.fromisoformat(l.get("timestamp", "")[:19]) >= cutoff_date
        ]
        
        # If no logs, compile a default empty trend
        if not recent_logs:
            return {
                "timestamps": [],
                "coherence_scores": [],
                "response_latencies": [],
                "outcomes": [],
                "medications": []
            }
            
        timestamps = []
        coherence_scores = []
        response_latencies = []
        outcomes = []
        medications = []
        
        for l in recent_logs:
            # Parse timestamp to simple readable date/time (e.g., "05-29 16:33")
            try:
                dt = datetime.datetime.fromisoformat(l.get("timestamp", ""))
                time_label = dt.strftime("%m-%d %H:%M")
            except ValueError:
                time_label = l.get("timestamp", "")[:16]
                
            timestamps.append(time_label)
            outcomes.append(l.get("outcome", "OTHER"))
            medications.append(l.get("medication", ""))
            
            # Coherence mapping fallback: if missing from logs, map from outcome
            coherence = l.get("coherence_score")
            if coherence is None:
                outcome = l.get("outcome", "OTHER")
                if outcome in ["TAKEN", "TAKEN_EARLIER"]:
                    coherence = 0.95
                elif outcome == "SNOOZE":
                    coherence = 0.85
                elif outcome == "CONFUSED":
                    coherence = 0.40
                elif outcome == "REFUSED":
                    coherence = 0.70
                elif outcome == "MEDICAL_CONCERN":
                    coherence = 0.50
                elif outcome == "NO_RESPONSE":
                    coherence = 0.20
                else:
                    coherence = 0.75
            coherence_scores.append(round(coherence, 2))
            
            # Latency mapping fallback
            latency = l.get("response_latency_sec")
            if latency is None:
                outcome = l.get("outcome", "OTHER")
                if outcome in ["TAKEN", "TAKEN_EARLIER"]:
                    latency = 3.2
                elif outcome == "SNOOZE":
                    latency = 4.5
                elif outcome == "CONFUSED":
                    latency = 9.5
                elif outcome == "REFUSED":
                    latency = 6.2
                elif outcome == "MEDICAL_CONCERN":
                    latency = 8.0
                elif outcome == "NO_RESPONSE":
                    latency = 12.0
                else:
                    latency = 5.0
            response_latencies.append(round(latency, 1))
            
        return {
            "timestamps": timestamps,
            "coherence_scores": coherence_scores,
            "response_latencies": response_latencies,
            "outcomes": outcomes,
            "medications": medications
        }
        
    @staticmethod
    def detect_decline(patient_name: str) -> bool:
        """
        Flags potential sudden health/cognitive decline.
        Returns True if the average coherence score drops by more than 20% in recent calls.
        """
        trend = CognitiveTracker.get_trend(patient_name, days=30)
        coherence_list = trend.get("coherence_scores", [])
        
        # Need at least 5 points to do an analytical comparison
        if len(coherence_list) < 5:
            return False
            
        # Compare the average of the last 3 calls vs prior calls (up to 10)
        recent_avg = np.mean(coherence_list[-3:])
        prior_avg = np.mean(coherence_list[:-3]) if len(coherence_list) > 3 else 0.85
        
        # Return True if recent score is 20%+ lower than prior average
        if prior_avg > 0 and (prior_avg - recent_avg) / prior_avg >= 0.20:
            return True
            
        return False
