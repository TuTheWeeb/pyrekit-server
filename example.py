from time import sleep

from flask import jsonify
from pyrekit_server import Server, ServerProcess


class App(Server):
    async def index(self):
        return "<h1>Hello World!</h1>", 200

    async def GET_json(self):
        return jsonify({"message": "Hello World"}), 200


if __name__ == "__main__":
    app = App(host="0.0.0.0", port=5000)
    server = ServerProcess(app)
    server.start()

    while True:
        try:
            sleep(0.5)
        except KeyboardInterrupt:
            print("Exiting...")
            server.close()
