"""A/B testing framework for optimizing recovery strategies."""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json


class TestStatus(Enum):
    """Test execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TestVariant:
    """Single variant in an A/B test."""

    name: str
    description: str
    parameters: Dict[str, Any]
    is_control: bool = False


@dataclass
class TestResult:
    """Result of a single test run."""

    variant_name: str
    timestamp: datetime
    metric_value: float
    metric_name: str
    success: bool
    notes: str = ""


class ABTestingFramework:
    """Manages A/B testing for recovery strategy optimization."""

    def __init__(self, logger=None):
        """Initialize A/B testing framework.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.tests: Dict[str, "ABTest"] = {}
        self.results_history: List[TestResult] = []

    def create_test(
        self,
        test_name: str,
        metric_name: str,
        control_params: Dict[str, Any],
        variant_params: List[Dict[str, Any]],
        duration_minutes: int = 60,
    ) -> "ABTest":
        """Create a new A/B test.

        Args:
            test_name: Name of the test
            metric_name: Metric to measure (e.g., 'lag_score')
            control_params: Parameters for control variant
            variant_params: List of parameters for test variants
            duration_minutes: How long to run test

        Returns:
            ABTest instance
        """
        test = ABTest(
            name=test_name,
            metric_name=metric_name,
            control_params=control_params,
            variant_params=variant_params,
            duration_minutes=duration_minutes,
            logger=self.logger,
        )

        self.tests[test_name] = test

        if self.logger:
            self.logger.info(f"Created A/B test: {test_name}")

        return test

    def run_test(
        self,
        test_name: str,
        metric_function: Callable[[Dict[str, Any]], float],
    ) -> Dict[str, Any]:
        """Execute an A/B test.

        Args:
            test_name: Name of test to run
            metric_function: Function to measure metric

        Returns:
            Test results dict
        """
        if test_name not in self.tests:
            return {"error": f"Test not found: {test_name}"}

        test = self.tests[test_name]
        results = test.run(metric_function)

        # Record results
        for result in results["individual_results"]:
            self.results_history.append(result)

        if self.logger:
            self.logger.info(f"Completed A/B test: {test_name}")

        return results

    def compare_variants(self, test_name: str) -> Dict[str, Any]:
        """Compare performance of variants in a test.

        Args:
            test_name: Test to analyze

        Returns:
            Comparison report
        """
        if test_name not in self.tests:
            return {"error": f"Test not found: {test_name}"}

        test = self.tests[test_name]
        return test.get_results_summary()

    def recommend_variant(self, test_name: str) -> Optional[str]:
        """Recommend best variant based on test results.

        Args:
            test_name: Test to analyze

        Returns:
            Recommended variant name or None
        """
        if test_name not in self.tests:
            return None

        test = self.tests[test_name]
        summary = test.get_results_summary()

        if not summary.get("results"):
            return None

        # Find variant with best average metric
        best_variant = None
        best_value = float("inf") if summary.get("metric_name") == "lag_score" else 0

        for variant_name, stats in summary["results"].items():
            avg_value = stats.get("average_value", 0)

            if summary.get("metric_name") == "lag_score":
                # Lower is better for lag_score
                if avg_value < best_value:
                    best_value = avg_value
                    best_variant = variant_name
            else:
                # Higher is better for other metrics
                if avg_value > best_value:
                    best_value = avg_value
                    best_variant = variant_name

        return best_variant

    def export_results(self, test_name: str, filepath: str) -> bool:
        """Export test results to file.

        Args:
            test_name: Test to export
            filepath: Path to write results

        Returns:
            True if successful
        """
        if test_name not in self.tests:
            return False

        test = self.tests[test_name]
        results = test.get_results_summary()

        try:
            with open(filepath, "w") as f:
                json.dump(results, f, indent=2, default=str)

            if self.logger:
                self.logger.info(f"Exported test results to {filepath}")

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error exporting results: {e}")
            return False

    def get_testing_report(self) -> Dict[str, Any]:
        """Get overall testing report.

        Returns:
            Report dict
        """
        return {
            "total_tests": len(self.tests),
            "total_results_recorded": len(self.results_history),
            "tests": {
                name: {
                    "status": test.status.value,
                    "metric": test.metric_name,
                    "runs": len(test.results),
                }
                for name, test in self.tests.items()
            },
        }


class ABTest:
    """Single A/B test execution."""

    def __init__(
        self,
        name: str,
        metric_name: str,
        control_params: Dict[str, Any],
        variant_params: List[Dict[str, Any]],
        duration_minutes: int = 60,
        logger=None,
    ):
        """Initialize A/B test.

        Args:
            name: Test name
            metric_name: Metric to measure
            control_params: Control variant parameters
            variant_params: List of variant parameters
            duration_minutes: Test duration
            logger: Logger instance
        """
        self.name = name
        self.metric_name = metric_name
        self.duration_minutes = duration_minutes
        self.logger = logger
        self.status = TestStatus.PENDING

        # Create variants
        self.variants = [
            TestVariant(
                name="control",
                description="Control variant",
                parameters=control_params,
                is_control=True,
            )
        ]

        for i, params in enumerate(variant_params):
            self.variants.append(
                TestVariant(
                    name=f"variant_{i+1}",
                    description=f"Test variant {i+1}",
                    parameters=params,
                    is_control=False,
                )
            )

        self.results: List[TestResult] = []
        self.start_time: Optional[datetime] = None

    def run(self, metric_function: Callable[[Dict[str, Any]], float]) -> Dict[str, Any]:
        """Run the A/B test.

        Args:
            metric_function: Function that takes variant params and returns metric value

        Returns:
            Results dict
        """
        self.status = TestStatus.RUNNING
        self.start_time = datetime.utcnow()
        individual_results = []

        for variant in self.variants:
            try:
                metric_value = metric_function(variant.parameters)

                result = TestResult(
                    variant_name=variant.name,
                    timestamp=datetime.utcnow(),
                    metric_value=metric_value,
                    metric_name=self.metric_name,
                    success=True,
                )

                self.results.append(result)
                individual_results.append(result)

                if self.logger:
                    self.logger.info(
                        f"Test {self.name}: {variant.name} = {metric_value:.2f}"
                    )

            except Exception as e:
                result = TestResult(
                    variant_name=variant.name,
                    timestamp=datetime.utcnow(),
                    metric_value=0,
                    metric_name=self.metric_name,
                    success=False,
                    notes=str(e),
                )

                self.results.append(result)
                individual_results.append(result)

                if self.logger:
                    self.logger.error(f"Test {self.name}: {variant.name} failed: {e}")

        self.status = TestStatus.COMPLETED

        return {
            "test_name": self.name,
            "metric_name": self.metric_name,
            "duration_minutes": self.duration_minutes,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.utcnow().isoformat(),
            "individual_results": individual_results,
            "summary": self.get_results_summary(),
        }

    def get_results_summary(self) -> Dict[str, Any]:
        """Get summary of test results.

        Returns:
            Summary dict
        """
        if not self.results:
            return {"results": {}}

        # Group results by variant
        variant_results = {}

        for result in self.results:
            if result.variant_name not in variant_results:
                variant_results[result.variant_name] = []
            variant_results[result.variant_name].append(result.metric_value)

        # Calculate statistics per variant
        summary = {
            "test_name": self.name,
            "metric_name": self.metric_name,
            "results": {},
        }

        for variant_name, values in variant_results.items():
            successful_values = [v for v in values if v > 0]

            summary["results"][variant_name] = {
                "count": len(values),
                "average_value": sum(successful_values) / len(successful_values)
                if successful_values
                else 0,
                "min_value": min(successful_values) if successful_values else 0,
                "max_value": max(successful_values) if successful_values else 0,
            }

        return summary
