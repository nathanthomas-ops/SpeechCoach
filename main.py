import os
import re
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import requests

# Initialize OpenAI client (will be None if API key not set)
try:
    client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
except:
    client = None

app = Flask(__name__)
s = requests.Session()  # Maintain session for cookies

TABROOM_LOGIN_URL = "https://www.tabroom.com/user/login/login.mhtml"
TABROOM_POST_URL = "https://www.tabroom.com/user/login/login_save.mhtml"

@app.route('/studentComments', methods=['POST'])
def studentComments():
  url = request.form['url']
  r2 = s.get(url)
  #print(r2.status_code)

  # Parse the HTML using BeautifulSoup
  soup = BeautifulSoup(r2.content, 'html.parser')

  # Find all div elements with class "full ltbordertop padvert"
  target_divs = soup.find_all('div', class_='full ltbordertop padvert')

  # Loop through each div element and extract text
  comments = []
  for target_div in target_divs:
    text = target_div.get_text(strip=True)
    comments.append(text)

  # Call LLM to summarize the comments
  instruction = "You are a speech coach. Using the feedback below, provide some action items for improvement on content and delivery. Add no formatting to your response."
  return openAI_gpt35(comments, instruction)

@app.route('/tournaments', methods=['GET'])
def tournamentResults():
  url = 'https://www.tabroom.com/user/student/index.mhtml?err=&msg='
  r1 = s.get(url)
  print(r1.status_code)

  # Parse the HTML using BeautifulSoup
  soup = BeautifulSoup(r1.content, 'html.parser')

  # Scrap links to tournaments results
  linksdos = soup.find_all('a', class_='buttonwhite smallish bluetext marvert padvertless fa fa-sm fa-file-text')
    #Finding tournament results links
  links = soup.find_all('a', class_='white full padvert')
    # for finding the names of the touneys
  links_data = []
  for i in range(0, len(links)):
      href = "https://www.tabroom.com/user/student/" + linksdos[i].get('href')
      text = links[i].get_text(strip=True)
      links_data.append({'href': href, 'text': text})

  return render_template('tournaments.html', links=links_data)

def openAI_gpt35(text, instruction):
  response = client.chat.completions.create(
      model="gpt-3.5-turbo",
      temperature=0.2,
      messages=[{
          "role": "system",
          "content": f"'{instruction}'"
      }, {
          "role": "user",
          "content": f"'{text}'"
      }])
  content = re.sub(r'\n', '<br>', response.choices[0].message.content)
  return render_template('openai_results.html', comments=content)

@app.route('/', methods=['GET'])  
def landing():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    user = request.form.get('username', '').strip()
    passwd = request.form.get('password', '').strip()

    if not user or not passwd:
        return render_template('login.html', error="Username and password are required.")

    try:
        # Step 1: Get the login page to retrieve CSRF tokens and form structure
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # Clear any existing cookies and start fresh
        s.cookies.clear()
        response = s.get(TABROOM_LOGIN_URL, headers=headers, timeout=10)

        if response.status_code != 200:
            return render_template('login.html', error="Unable to connect to Tabroom. Try again later.")

        # Step 2: Parse the form and extract all necessary fields
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the login form
        login_form = soup.find('form')
        if not login_form:
            return render_template('login.html', error="Unable to find login form on Tabroom.")
        
        # Extract all hidden input fields
        payload = {}
        for input_field in login_form.find_all('input', type='hidden'):
            name = input_field.get('name')
            value = input_field.get('value', '')
            if name:
                payload[name] = value
        
        # Add credentials - try both common field names
        payload['username'] = user
        payload['password'] = passwd
        payload['email'] = user  # Some sites use email instead of username
        payload['passwd'] = passwd  # Some sites use passwd instead of password
        
        #print(f"Login payload: {payload}")

        # Step 3: Send the login request
        login_response = s.post(TABROOM_POST_URL, data=payload, headers=headers, allow_redirects=True, timeout=10)

        #print(f"Login response status: {login_response.status_code}")
        #print(f"Login response URL: {login_response.url}")

        # Step 4: Check for various success indicators
        response_text = login_response.text.lower()
        
        # Check for error messages
        if any(error in response_text for error in [
            "incorrect username", "incorrect password", "not correct", 
            "invalid login", "login failed", "authentication failed"
        ]):
            return render_template('login.html', error="Invalid username or password. Please verify your Tabroom credentials.")
        
        # Check for success indicators
        if any(success in login_response.url for success in [
            "student/index", "user/student", "dashboard", "home"
        ]) or any(success in response_text for success in [
            "student dashboard", "welcome", "tournaments", "logout"
        ]):
            return tournamentResults()
        
        # If we're still on the login page, it likely failed
        if "login" in login_response.url:
            return render_template('login.html', error="Login failed. Please check your credentials and try again.")
        
        # Last resort - try to access the student dashboard directly
        dashboard_response = s.get("https://www.tabroom.com/user/student/index.mhtml", headers=headers, timeout=10)
        if dashboard_response.status_code == 200 and "student" in dashboard_response.text.lower():
            return tournamentResults()
        
        return render_template('login.html', error="Unable to verify login. Please try again.")

    except requests.exceptions.Timeout:
        return render_template('login.html', error="Request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        print(f"Login error: {e}")
        return render_template('login.html', error="Network error. Please check your connection and try again.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        return render_template('login.html', error="An unexpected error occurred. Please try again.")


@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

app.run(host='0.0.0.0')