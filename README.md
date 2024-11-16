## Server startup

### 1. Prerequisites
- Python 3

### 2. Preparation
#### 2.1 Create python virtual environment
    python -m venv venv
#### 2.2 Activate vitrual environment
    source ./venv/bin/activate
    (Or a similar command for your command shell)
#### 2.3 Update pip
    pip install --upgrade pip
#### 2.4 Install all the project dependencies
    pip install -r requirements.txt

### 3. Startup
    fastapi dev main.py
