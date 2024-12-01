## Server startup

### 1. Prerequisites
- Python 3

### 2. Preparation
#### 2.1 Create python virtual environment
    python -m venv venv
#### 2.2 Activate vitrual environment
##### Linux / WSL
    source ./venv/bin/activate
##### Windows
    venv\Scripts\Activate
#### 2.3 Update pip
    pip install --upgrade pip
#### 2.4 Install all the project dependencies
    pip install -r requirements.txt

### 3. Startup
    fastapi dev main.py


## Setup server access from outside (Windows)

1. Do steps 2.1 - 2.4 from "Server startup" part.
2. Start the server with the following command:
    ```
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```
3. Open `cmd.exe`, execute the following command, and memorize the last number from the output. It is the process ID (PID).
    ```
    netstat -ao | find /i "listening" | find /i "8000"
    ```
4. Open `Task Manager` and switch to the `Details` tab. look for the PID from the previous step.
5. Once you found it, right click it and choose `Open file location`. Copy the path.
6. Navigate to Settings > Network & Internet > Status > Windows Firewall.
7. Choose `Allow an app through firewall`, then `Change settings` (with an admin sign). Click `Allow another app...` and `Browse...`.
8. Paste the previously copied path to the top bar and select the approppriate .exe file (that was listed in the task manager). Click `Add`.
9. Tick the checkbox in the `Private` column (and in the `Public` column also, if you wish). Click `OK` at the bottom.
10. Done!
