from app import App

app = App()
app.init()

def lambda_handler(event, context):
    app.run()