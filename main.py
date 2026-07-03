import nano
app = nano.nano  # Vercel's Python runtime serves the ASGI `app` exported from main.py
if __name__ == "__main__": nano.launch()
