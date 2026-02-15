try:
    import numpy as np
    print(f"NumPy: {np.__version__}")
except ImportError as e:
    print(f"NumPy Error: {e}")

try:
    import pandas as pd
    print(f"Pandas: {pd.__version__}")
except ImportError as e:
    print(f"Pandas Error: {e}")

try:
    import skopt
    from skopt import gp_minimize
    print(f"Skopt: {skopt.__version__}")
    # Quick fix check for np.int issue
    if np.__version__ >= '1.20':
        print("Note: NumPy >= 1.20 might cause issues with skopt if it uses np.int")
except ImportError as e:
    print(f"Skopt Error: {e}")
except Exception as e:
    print(f"Skopt Runtime Error: {e}")
    
try:
    import ta
    print(f"TA: {ta.__version__}")
except ImportError as e:
    print(f"TA Error: {e}")
