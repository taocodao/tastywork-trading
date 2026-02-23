import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class ConfidenceGatedDecisionMaker:
    """
    Routes decisions between ML and rule-based systems.
    
    - Below confidence threshold -> rule-based fallback
    - Above threshold -> ML decision
    - Tracks ML vs rule-based performance for A/B comparison
    - Logs all decisions and outcomes for continuous learning
    """
    
    def __init__(self, confidence_threshold: float = 0.70):
        self.threshold = confidence_threshold
        
    def decide(self, 
               ml_output: Any, 
               rule_output: Any, 
               ml_confidence: float, 
               decision_context: str = "general") -> Dict[str, Any]:
        """
        Make a gated decision based on ML model confidence.
        
        Args:
            ml_output: The decision proposed by the ML model
            rule_output: The fallback decision proposed by the deterministic rules
            ml_confidence: The probability/confidence score from the ML model (0.0 - 1.0)
            decision_context: String categorizing the decision (e.g., 'ENTRY_GATING', 'ROLL_TIMING')
            
        Returns:
            Dict containing the final decision and metadata for logging
        """
        decision_source = "RULE_BASED"
        final_decision = rule_output
        
        # If ML is confident enough, we trust its output
        if ml_confidence >= self.threshold and ml_output is not None:
            decision_source = "ML_MODEL"
            final_decision = ml_output
            
        logger.info(f"[{decision_context}] Decision routed to {decision_source} (ML Confidence: {ml_confidence:.2f})")
        
        return {
            "decision": final_decision,
            "source": decision_source,
            "confidence": ml_confidence,
            "rule_based_alternative": rule_output,
            "context": decision_context
        }

