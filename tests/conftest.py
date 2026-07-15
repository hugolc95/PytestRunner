import os, sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
