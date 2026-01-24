"""
Vertical Spread API Routes
==========================

API endpoints for vertical spread signals and trading.
"""

from flask import Blueprint, request, jsonify
import logging
from datetime import date

logger = logging.getLogger(__name__)

vertical_bp = Blueprint('vertical', __name__, url_prefix='/api/vertical')


# Import vertical spread modules
try:
    from src.vertical_spreads.direction_predictor import VerticalSpreadDirectionPredictor
    from src.vertical_spreads.spread_selector import VerticalSpreadSelector, get_available_expirations
    from src.vertical_spreads.signal_generator import VerticalSpreadSignalGenerator, signal_to_dict
    from src.vertical_spreads.suitability import VerticalSpreadSuitabilityValidator
    from src.vertical_spreads.stop_manager import VerticalSpreadStopManager
    from signal_publisher import (
        publish_buy_signal,
        publish_sell_signal,
        publish_warning_signal,
        get_vertical_spread_signals,
        SignalType
    )
    MODULES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Vertical spread modules not fully available: {e}")
    MODULES_AVAILABLE = False


@vertical_bp.route('/signals', methods=['GET'])
def get_signals():
    """
    Get pending vertical spread signals.
    
    Query params:
        type: Filter by signal type (BUY, SELL, WARNING)
        
    Returns:
        List of signals
    """
    signal_type = request.args.get('type', '').upper() or None
    
    if MODULES_AVAILABLE:
        signals = get_vertical_spread_signals(signal_type)
        return jsonify({
            "success": True,
            "count": len(signals),
            "signals": signals
        })
    else:
        return jsonify({"success": False, "error": "Modules not available"}), 500


@vertical_bp.route('/generate', methods=['POST'])
def generate_signal():
    """
    Generate a vertical spread signal for a symbol.
    
    Request body:
        symbol: Stock symbol (required)
        price: Current stock price (required)
        rsi_14: RSI value (optional, defaults to 50)
        iv: Implied volatility (optional, defaults to 0.25)
        account_balance: Account balance (optional, defaults to 5000)
        
    Returns:
        Generated signal or reason for no signal
    """
    if not MODULES_AVAILABLE:
        return jsonify({"success": False, "error": "Modules not available"}), 500
    
    data = request.get_json() or {}
    symbol = data.get('symbol', 'SPY')
    
    # Build stock data
    stock_data = {
        "symbol": symbol,
        "price": data.get('price', 485.0),
        "rsi_14": data.get('rsi_14', 50),
        "bb_upper": data.get('bb_upper'),
        "bb_mid": data.get('bb_mid'),
        "bb_lower": data.get('bb_lower'),
        "sma_20": data.get('sma_20'),
        "sma_50": data.get('sma_50'),
        "sma_200": data.get('sma_200'),
        "iv": data.get('iv', 0.25)
    }
    
    # Fill missing BB/SMA with reasonable defaults
    price = stock_data['price']
    if not stock_data['bb_upper']:
        stock_data['bb_upper'] = price * 1.02
    if not stock_data['bb_mid']:
        stock_data['bb_mid'] = price
    if not stock_data['bb_lower']:
        stock_data['bb_lower'] = price * 0.98
    if not stock_data['sma_20']:
        stock_data['sma_20'] = price
    if not stock_data['sma_50']:
        stock_data['sma_50'] = price * 0.99
    if not stock_data['sma_200']:
        stock_data['sma_200'] = price * 0.97
    
    # Account data
    account_data = {
        "balance": data.get('account_balance', 5000),
        "risk_tolerance": data.get('risk_tolerance', 'medium'),
        "options_level": data.get('options_level', 2)
    }
    
    try:
        generator = VerticalSpreadSignalGenerator()
        signal = generator.generate_signal(symbol, stock_data, account_data)
        
        if signal and signal.status != "rejected":
            # Publish the signal
            publish_buy_signal(signal)
            
            return jsonify({
                "success": True,
                "signal": signal_to_dict(signal),
                "published": True
            })
        elif signal and signal.status == "rejected":
            return jsonify({
                "success": True,
                "signal": None,
                "reason": signal.rationale
            })
        else:
            return jsonify({
                "success": True,
                "signal": None,
                "reason": "No actionable signal generated"
            })
            
    except Exception as e:
        logger.error(f"Error generating signal: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@vertical_bp.route('/direction', methods=['POST'])
def get_direction():
    """
    Get direction prediction for a symbol (without generating full signal).
    
    Request body:
        symbol: Stock symbol
        price: Current price
        rsi_14: RSI value
        (other technical indicators)
        
    Returns:
        Direction (BULL/BEAR/NEUTRAL), confidence, reasoning
    """
    if not MODULES_AVAILABLE:
        return jsonify({"success": False, "error": "Modules not available"}), 500
    
    data = request.get_json() or {}
    
    predictor = VerticalSpreadDirectionPredictor()
    signal = predictor.calculate_direction_signal(data)
    
    return jsonify({
        "success": True,
        "direction": signal.direction,
        "confidence": signal.confidence,
        "reasoning": signal.reasoning,
        "actionable": predictor.is_actionable(signal),
        "indicators": signal.indicators
    })


@vertical_bp.route('/suitability', methods=['POST'])
def check_suitability():
    """
    Check if customer is suitable for vertical spread trading.
    
    Request body:
        account_balance: Account balance
        options_level: Options approval level (1-4)
        
    Returns:
        Suitability result with checks
    """
    if not MODULES_AVAILABLE:
        return jsonify({"success": False, "error": "Modules not available"}), 500
    
    data = request.get_json() or {}
    
    validator = VerticalSpreadSuitabilityValidator()
    result = validator.validate(data)
    
    return jsonify({
        "success": True,
        "suitable": result.suitable,
        "checks": result.to_dict()['checks'],
        "blockingIssues": result.blocking_issues,
        "warnings": result.warnings
    })


@vertical_bp.route('/publish/buy', methods=['POST'])
def publish_buy():
    """
    Manually publish a BUY signal.
    
    Request body:
        symbol, strategy, buyStrike, sellStrike, etc.
    """
    if not MODULES_AVAILABLE:
        return jsonify({"success": False, "error": "Modules not available"}), 500
    
    data = request.get_json() or {}
    success = publish_buy_signal(data)
    
    return jsonify({"success": success, "signalType": "BUY"})


@vertical_bp.route('/publish/sell', methods=['POST'])
def publish_sell():
    """
    Manually publish a SELL signal.
    
    Request body:
        symbol, reason, position data
    """
    if not MODULES_AVAILABLE:
        return jsonify({"success": False, "error": "Modules not available"}), 500
    
    data = request.get_json() or {}
    reason = data.pop('reason', '')
    success = publish_sell_signal(data, reason)
    
    return jsonify({"success": success, "signalType": "SELL"})


@vertical_bp.route('/publish/warning', methods=['POST'])
def publish_warning():
    """
    Manually publish a WARNING signal.
    
    Request body:
        symbol: Stock symbol
        message: Warning message
        data: Optional additional data
    """
    if not MODULES_AVAILABLE:
        return jsonify({"success": False, "error": "Modules not available"}), 500
    
    req = request.get_json() or {}
    symbol = req.get('symbol', 'UNKNOWN')
    message = req.get('message', 'Warning')
    data = req.get('data', {})
    
    success = publish_warning_signal(symbol, message, data)
    
    return jsonify({"success": success, "signalType": "WARNING"})


@vertical_bp.route('/health', methods=['GET'])
def health():
    """Health check for vertical spread API."""
    return jsonify({
        "status": "ok",
        "modulesAvailable": MODULES_AVAILABLE,
        "signalTypes": ["BUY", "SELL", "WARNING"],
        "channels": [
            "vertical_spread",
            "vertical_spread.buy",
            "vertical_spread.sell",
            "vertical_spread.warning"
        ]
    })
