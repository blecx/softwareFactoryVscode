"""
Learning confidence scoring for filtering and prioritizing relevant learnings.

This module scores learnings based on recency, domain match, repository match,
success rate, and application frequency to ensure agents apply the most
relevant learnings to current issues.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Learning:
    """Represents a single learning entry with metadata."""

    content: str
    timestamp: datetime
    domain: str  # e.g., "backend", "frontend", "testing"
    repository: str  # e.g., "factory", "factory-Client"
    success_rate: float = 1.0  # 0.0 to 1.0
    application_count: int = 0
    issue_number: Optional[int] = None


@dataclass
class ScoredLearning:
    """Learning with computed relevance score."""

    learning: Learning
    score: float
    score_breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass
class ScoringMetrics:
    """Metrics for learning scorer performance."""

    learning_relevance_score_avg: float = 0.0
    irrelevant_learnings_filtered: int = 0
    total_learnings_scored: int = 0
    top_score: float = 0.0


class LearningScorer:
    """
    Scores and filters learnings based on relevance to current context.

    Scoring factors:
    - Recency: 90-day half-life decay (newer = more relevant)
    - Domain match: 1.0 if exact match, 0.3 otherwise
    - Repository match: 1.0 if exact match, 0.5 otherwise
    - Success rate: Historical success of this learning
    - Application frequency: Number of times successfully applied

    Final score = weighted average of factors
    Threshold: 0.3 (filter out low-relevance learnings)

    Metrics tracked:
    - learning_relevance_score_avg: Average score of relevant learnings
    - irrelevant_learnings_filtered: Count of learnings below threshold
    """

    def __init__(
        self,
        recency_half_life_days: int = 90,
        relevance_threshold: float = 0.3,
        weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize learning scorer.

        Args:
            recency_half_life_days: Days for recency score to decay by half
            relevance_threshold: Minimum score to consider learning relevant
            weights: Custom weights for scoring factors (default: equal)
        """
        self.recency_half_life_days = recency_half_life_days
        self.relevance_threshold = relevance_threshold

        # Default weights (can be customized)
        self.weights = weights or {
            "recency": 0.3,
            "domain": 0.25,
            "repository": 0.2,
            "success_rate": 0.15,
            "frequency": 0.1,
        }

        # Validate weights sum to ~1.0
        weight_sum = sum(self.weights.values())
        if not (0.99 <= weight_sum <= 1.01):
            raise ValueError(f"Weights must sum to 1.0, got {weight_sum}")

        self.metrics = ScoringMetrics()

    def compute_recency_score(self, learning: Learning, now: datetime) -> float:
        """
        Compute recency score using exponential decay.

        Score = 0.5 ^ (days_old / half_life_days)

        Args:
            learning: Learning to score
            now: Current timestamp

        Returns:
            Recency score (0.0 to 1.0)
        """
        days_old = (now - learning.timestamp).days
        if days_old < 0:
            days_old = 0

        # Exponential decay with half-life
        score = math.pow(0.5, days_old / self.recency_half_life_days)
        return min(1.0, score)  # Cap at 1.0

    def compute_domain_score(self, learning: Learning, current_domain: str) -> float:
        """
        Compute domain match score.

        Args:
            learning: Learning to score
            current_domain: Current issue domain

        Returns:
            Domain score (0.3 to 1.0)
        """
        if learning.domain.lower() == current_domain.lower():
            return 1.0
        return 0.3  # Partial credit for cross-domain learnings

    def compute_repository_score(
        self, learning: Learning, current_repository: str
    ) -> float:
        """
        Compute repository match score.

        Args:
            learning: Learning to score
            current_repository: Current repository name

        Returns:
            Repository score (0.5 to 1.0)
        """
        if learning.repository.lower() == current_repository.lower():
            return 1.0
        return 0.5  # Partial credit for cross-repo learnings

    def compute_success_score(self, learning: Learning) -> float:
        """
        Compute success rate score.

        Args:
            learning: Learning with success_rate

        Returns:
            Success score (0.0 to 1.0)
        """
        return max(0.0, min(1.0, learning.success_rate))

    def compute_frequency_score(self, learning: Learning) -> float:
        """
        Compute application frequency score.

        Score increases with application count but with diminishing returns.
        Score = 1 - (1 / (1 + log(1 + application_count)))

        Args:
            learning: Learning with application_count

        Returns:
            Frequency score (0.0 to 1.0)
        """
        if learning.application_count == 0:
            return 0.0

        # Logarithmic scale for diminishing returns
        score = 1.0 - (1.0 / (1.0 + math.log(1.0 + learning.application_count)))
        return min(1.0, score)

    def score_learning(
        self,
        learning: Learning,
        current_domain: str,
        current_repository: str,
        now: Optional[datetime] = None,
    ) -> ScoredLearning:
        """
        Compute relevance score for a learning.

        Args:
            learning: Learning to score
            current_domain: Current issue domain
            current_repository: Current repository
            now: Current timestamp (default: datetime.now())

        Returns:
            ScoredLearning with final score and breakdown
        """
        if now is None:
            now = datetime.now()

        # Compute individual scores
        recency = self.compute_recency_score(learning, now)
        domain = self.compute_domain_score(learning, current_domain)
        repository = self.compute_repository_score(learning, current_repository)
        success = self.compute_success_score(learning)
        frequency = self.compute_frequency_score(learning)

        # Weighted average
        final_score = (
            self.weights["recency"] * recency
            + self.weights["domain"] * domain
            + self.weights["repository"] * repository
            + self.weights["success_rate"] * success
            + self.weights["frequency"] * frequency
        )

        breakdown = {
            "recency": recency,
            "domain": domain,
            "repository": repository,
            "success_rate": success,
            "frequency": frequency,
            "final": final_score,
        }

        return ScoredLearning(
            learning=learning, score=final_score, score_breakdown=breakdown
        )

    def get_relevant_learnings(
        self,
        learnings: List[Learning],
        current_domain: str,
        current_repository: str,
        now: Optional[datetime] = None,
    ) -> List[ScoredLearning]:
        """
        Filter and sort learnings by relevance score.

        Args:
            learnings: List of learnings to score
            current_domain: Current issue domain
            current_repository: Current repository
            now: Current timestamp

        Returns:
            List of ScoredLearning sorted by score (highest first),
            filtered by relevance threshold
        """
        scored = [
            self.score_learning(learning, current_domain, current_repository, now)
            for learning in learnings
        ]

        # Filter by threshold
        relevant = [s for s in scored if s.score >= self.relevance_threshold]
        irrelevant_count = len(scored) - len(relevant)

        # Sort by score descending
        relevant.sort(key=lambda x: x.score, reverse=True)

        # Update metrics
        self.metrics.total_learnings_scored = len(scored)
        self.metrics.irrelevant_learnings_filtered = irrelevant_count
        if relevant:
            self.metrics.learning_relevance_score_avg = sum(
                s.score for s in relevant
            ) / len(relevant)
            self.metrics.top_score = relevant[0].score
        else:
            self.metrics.learning_relevance_score_avg = 0.0
            self.metrics.top_score = 0.0

        return relevant

    def get_metrics(self) -> Dict[str, float]:
        """Get current metrics as dictionary."""
        return {
            "learning_relevance_score_avg": self.metrics.learning_relevance_score_avg,
            "irrelevant_learnings_filtered": self.metrics.irrelevant_learnings_filtered,
            "total_learnings_scored": self.metrics.total_learnings_scored,
            "top_score": self.metrics.top_score,
        }


def get_learning_scorer(
    recency_half_life_days: int = 90,
    relevance_threshold: float = 0.3,
    weights: Optional[Dict[str, float]] = None,
) -> LearningScorer:
    """
    Convenience factory function for creating LearningScorer instance.

    Args:
        recency_half_life_days: Days for recency decay
        relevance_threshold: Minimum score for relevance
        weights: Custom scoring weights

    Returns:
        LearningScorer instance
    """
    return LearningScorer(
        recency_half_life_days=recency_half_life_days,
        relevance_threshold=relevance_threshold,
        weights=weights,
    )
