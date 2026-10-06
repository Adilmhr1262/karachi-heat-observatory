Publish the dashboard as a real website (Hugging Face Spaces)
===============================================================

Free, no credit card. You get a public URL like
https://YOURNAME-karachi-heat-observatory.hf.space

One-time setup (15 minutes):

1. Sign up at huggingface.co. Create an access token:
   Profile picture > Settings > Access Tokens > New token (role: Write).
   Copy the token.

2. On your MacBook, in Terminal:
   pip install huggingface_hub
   hf auth login
   (paste the token when asked)

3. Create the Space (in your browser):
   huggingface.co > New Space.
   Name: karachi-heat-observatory. SDK: Streamlit. Visibility: Public.
   Leave the template files, you will overwrite them.

4. Push this project to the Space (in Terminal):
   cd karachi-heat-observatory
   git init -b main
   git lfs install
   git lfs track "*.tif"
   hf upload YOURNAME/karachi-heat-observatory . .
   (replace YOURNAME with your Hugging Face username)

   The 700 MB of map data uploads through git-lfs. Takes a while once.

5. Open the Space page. It builds automatically (5-15 minutes, it installs
   the Python packages). When the build finishes, your dashboard is live
   at the public URL.

Notes:
- The Space sleeps when idle and wakes on visit (free tier). First visit
  after idle takes ~30 seconds.
- If the build fails on memory, tell me and I will trim the requirements.
- The README.md already carries the Space metadata block at the top.
