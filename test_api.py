import requests, json, sys
base = 'http://127.0.0.1:5000'
login = requests.post(f'{base}/api/auth/login', json={'email':'cardio1@mediguard.local','password':'cardiologist'})
print('Login status', login.status_code)
print('Login body', login.text)
if login.status_code != 200:
    sys.exit(1)
# token extraction (API returns data wrapper)
resp_json = login.json()
# The login endpoint returns {'status':'success','data':auth_result}
# auth_result contains access_token
access_token = resp_json.get('data', {}).get('access_token')
print('Token', access_token)
if not access_token:
    sys.exit(1)
headers = {'Authorization': f'Bearer {access_token}'}
stats = requests.get(f'{base}/api/dashboard/stats', headers=headers)
print('Stats status', stats.status_code)
print('Stats body', stats.text)
patients = requests.get(f'{base}/api/patients', headers=headers)
print('Patients status', patients.status_code)
print('Patients body', patients.text)
