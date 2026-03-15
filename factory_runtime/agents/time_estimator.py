"""ML-based time estimation for agent issues.

Uses RandomForestRegressor trained on historical data to predict issue
resolution time with confidence scoring.
"""

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split


@dataclass
class TimeEstimate:
    """Time estimation result with confidence and reasoning."""

    hours: float
    confidence: float  # 0-1 score
    reasoning: str
    features_used: Dict[str, float]


class TimeEstimator:
    """ML-based time estimator using RandomForestRegressor.

    Features:
    - files_to_change: Number of files to modify
    - lines_estimate: Estimated total lines changed
    - domain: Encoded domain (backend, frontend, docs, etc.)
    - is_multi_repo: Boolean for cross-repo work
    - has_dependencies: Boolean for dependency on other issues
    - complexity_score: 1-5 subjective complexity

    Usage:
        estimator = TimeEstimator()
        estimator.train_from_knowledge_base()

        estimate = estimator.predict(
            files_to_change=5,
            lines_estimate=200,
            domain="backend",
            is_multi_repo=False,
            has_dependencies=False,
            complexity_score=3
        )

        print(f"Estimated: {estimate.hours:.1f}h "
              f"(confidence: {estimate.confidence:.0%})")
        print(f"Reasoning: {estimate.reasoning}")
    """

    DOMAINS = ["backend", "frontend", "docs", "testing", "ci", "agent", "other"]

    def __init__(self, model_path: Optional[Path] = None):
        """Initialize estimator with optional pre-trained model."""
        self.model = RandomForestRegressor(
            n_estimators=50, max_depth=10, random_state=42, min_samples_split=3
        )
        self.is_trained = False
        self.feature_names = [
            "files_to_change",
            "lines_estimate",
            "is_multi_repo",
            "has_dependencies",
            "complexity_score",
        ] + [f"domain_{d}" for d in self.DOMAINS]

        self.mae = None  # Mean Absolute Error on validation set

        if model_path and model_path.exists():
            self.load_model(model_path)

    def _encode_domain(self, domain: str) -> List[int]:
        """One-hot encode domain."""
        return [1 if domain == d else 0 for d in self.DOMAINS]

    def _extract_features(
        self,
        files_to_change: int,
        lines_estimate: int,
        domain: str,
        is_multi_repo: bool,
        has_dependencies: bool,
        complexity_score: int,
    ) -> np.ndarray:
        """Extract feature vector from issue attributes."""
        features = [
            files_to_change,
            lines_estimate,
            int(is_multi_repo),
            int(has_dependencies),
            complexity_score,
        ]
        features.extend(self._encode_domain(domain))
        return np.array(features).reshape(1, -1)

    def train(
        self,
        training_data: List[Dict],
        validation_split: float = 0.2,
    ) -> Dict[str, float]:
        """Train model on historical data.

        Args:
            training_data: List of dicts with keys:
                - files_to_change, lines_estimate, domain,
                  is_multi_repo, has_dependencies, complexity_score,
                  actual_hours
            validation_split: Fraction for validation set

        Returns:
            Metrics dict with mae, train_mae, val_mae, samples
        """
        if len(training_data) < 5:
            raise ValueError(f"Need at least 5 samples, got {len(training_data)}")

        # Extract features and targets
        X = []
        y = []
        for data in training_data:
            features = self._extract_features(
                data["files_to_change"],
                data["lines_estimate"],
                data.get("domain", "other"),
                data.get("is_multi_repo", False),
                data.get("has_dependencies", False),
                data.get("complexity_score", 3),
            )
            X.append(features.flatten())
            y.append(data["actual_hours"])

        X = np.array(X)
        y = np.array(y)

        # Split and train
        if len(X) >= 10:
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=validation_split, random_state=42
            )
            self.model.fit(X_train, y_train)

            train_mae = mean_absolute_error(y_train, self.model.predict(X_train))
            val_mae = mean_absolute_error(y_val, self.model.predict(X_val))
            self.mae = val_mae
        else:
            # Too few samples for split, use all for training
            self.model.fit(X, y)
            train_mae = mean_absolute_error(y, self.model.predict(X))
            val_mae = train_mae
            self.mae = train_mae

        self.is_trained = True

        return {
            "mae": self.mae,
            "train_mae": train_mae,
            "val_mae": val_mae,
            "samples": len(training_data),
        }

    def train_from_knowledge_base(
        self, kb_path: Path = Path("agents/knowledge")
    ) -> Dict[str, float]:
        """Train from knowledge base JSON files.

        Expects files like issue_resolutions.json with historical data.
        """
        training_data = []

        # Load from all KB files
        for kb_file in kb_path.glob("*.json"):
            try:
                with open(kb_file) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for entry in data:
                            if "actual_hours" in entry:
                                training_data.append(entry)
            except (json.JSONDecodeError, KeyError):
                continue

        if not training_data:
            # No historical data, use synthetic defaults for cold start
            training_data = self._get_default_training_data()

        return self.train(training_data)

    def _get_default_training_data(self) -> List[Dict]:
        """Generate synthetic training data for cold start."""
        # Based on historical averages from project experience
        return [
            {
                "files_to_change": 2,
                "lines_estimate": 50,
                "domain": "backend",
                "complexity_score": 1,
                "actual_hours": 1.5,
            },
            {
                "files_to_change": 5,
                "lines_estimate": 200,
                "domain": "backend",
                "complexity_score": 2,
                "actual_hours": 3.0,
            },
            {
                "files_to_change": 3,
                "lines_estimate": 100,
                "domain": "frontend",
                "complexity_score": 2,
                "actual_hours": 2.5,
            },
            {
                "files_to_change": 10,
                "lines_estimate": 500,
                "domain": "backend",
                "is_multi_repo": True,
                "complexity_score": 4,
                "actual_hours": 8.0,
            },
            {
                "files_to_change": 1,
                "lines_estimate": 20,
                "domain": "docs",
                "complexity_score": 1,
                "actual_hours": 0.5,
            },
            {
                "files_to_change": 4,
                "lines_estimate": 150,
                "domain": "testing",
                "complexity_score": 2,
                "actual_hours": 2.0,
            },
            {
                "files_to_change": 8,
                "lines_estimate": 400,
                "domain": "agent",
                "has_dependencies": True,
                "complexity_score": 3,
                "actual_hours": 6.0,
            },
        ]

    def predict(
        self,
        files_to_change: int,
        lines_estimate: int,
        domain: str = "other",
        is_multi_repo: bool = False,
        has_dependencies: bool = False,
        complexity_score: int = 3,
    ) -> TimeEstimate:
        """Predict time estimate with confidence and reasoning."""
        if not self.is_trained:
            self.train_from_knowledge_base()

        features = self._extract_features(
            files_to_change,
            lines_estimate,
            domain,
            is_multi_repo,
            has_dependencies,
            complexity_score,
        )

        # Get prediction
        hours = float(self.model.predict(features)[0])

        # Calculate confidence (inverse of MAE relative to prediction)
        if self.mae and hours > 0:
            confidence = max(0.0, min(1.0, 1.0 - (self.mae / max(hours, 0.1))))
        else:
            confidence = 0.5  # Medium confidence if no MAE

        # Generate reasoning
        reasoning = self._generate_reasoning(
            files_to_change,
            lines_estimate,
            domain,
            is_multi_repo,
            has_dependencies,
            complexity_score,
            hours,
        )

        features_dict = dict(zip(self.feature_names, features.flatten()))

        return TimeEstimate(
            hours=hours,
            confidence=confidence,
            reasoning=reasoning,
            features_used=features_dict,
        )

    def _generate_reasoning(
        self,
        files_to_change: int,
        lines_estimate: int,
        domain: str,
        is_multi_repo: bool,
        has_dependencies: bool,
        complexity_score: int,
        predicted_hours: float,
    ) -> str:
        """Generate human-readable reasoning for estimate."""
        reasons = []

        if files_to_change > 5:
            reasons.append(f"{files_to_change} files to change (high)")
        if lines_estimate > 300:
            reasons.append(f"{lines_estimate} lines (large change)")
        if is_multi_repo:
            reasons.append("multi-repo coordination needed")
        if has_dependencies:
            reasons.append("depends on other issues")
        if complexity_score >= 4:
            reasons.append(f"complexity {complexity_score}/5 (high)")
        if domain == "backend":
            reasons.append("backend work (API + tests)")
        elif domain == "frontend":
            reasons.append("frontend work (UI + styling)")

        if not reasons:
            reasons.append(f"{domain} domain, complexity {complexity_score}/5")

        return f"Estimated {predicted_hours:.1f}h based on: " + ", ".join(reasons)

    def save_model(self, path: Path) -> None:
        """Save trained model to disk."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "model": self.model,
                    "mae": self.mae,
                    "feature_names": self.feature_names,
                },
                f,
            )

    def load_model(self, path: Path) -> None:
        """Load pre-trained model from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self.mae = data.get("mae")
            self.feature_names = data.get("feature_names", self.feature_names)
            self.is_trained = True

    def get_metrics(self) -> Dict[str, float]:
        """Get model performance metrics."""
        return {
            "mae": self.mae if self.mae else 0.0,
            "is_trained": self.is_trained,
        }
