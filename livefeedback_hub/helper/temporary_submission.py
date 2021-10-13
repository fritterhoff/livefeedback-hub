class TemporarySubmission:
    user_hash = ""
    id = ""
    autograder_zip = bytes()
    notebook = bytes()

    def __init__(self, notebook, autograder_zip, id, user_hash):
        self.id = id
        self.autograder_zip = autograder_zip
        self.notebook = notebook
        self.user_hash = user_hash
