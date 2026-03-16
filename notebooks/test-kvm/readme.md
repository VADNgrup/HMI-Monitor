# KVM API Access Script

This simple script allows you to interact with the KVM system via HTTP APIs for connection, status check, screen capture, and mouse control.

---

## STEPS

### 1. Run WireGuard VPN connection to KVM network
Please setup the vpn according to provided documents on teams. Check connection to the endpoint in terminal as
```bash
# sudo wg-quick up kvm-wg0
ping 10.128.0.4 # check 

```

### 2. CHECK API BY checking_api.sh

- Run this cript on ubuntu or powershell
```bash
bash checking_api.sh
```

---

- 

### 3. Run API data crawler
Must ensure you can connect to the API by step 2

Then install the environment first:

```
pip install -r reqs.txt
```

finally, run  my script:

```python
python interaction.py
```


The logic of using API is :
- Step1: we have to use to `connect API` to create a session.
- Step2: Then you can call `snapshot API` to cralw data and save it. or `mouse move` API to wake up screen if it turn off. **NOTE** You have to use the created session by Step 1 to send new request
- Step3: Turn off connection --> dele session. Actually, even you not call this API, the session also will be terminated after a while.

Check my code to understand more... (>.<)

