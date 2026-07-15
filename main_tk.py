import tkinter as tk
from PyTestRunner import PyTestGUI


if __name__ == "__main__":
    root = tk.Tk()
    app = PyTestGUI(root)
    root.mainloop()
