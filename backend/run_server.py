#!/usr/bin/env python
"""Run the FastAPI server - Windows compatible"""
import os
import sys
from multiprocessing import freeze_support

if __name__ == '__main__':
    freeze_support()

    # Change to backend directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    # Run uvicorn
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
