import pymongo


host = "5.23.53.172"
port = 27777

username = "admin"
password = "322228"

# Формирование строки подключения с логином и паролем
connection_string = f"mongodb://{username}:{password}@{host}:{port}/"
# connection_string = f"mongodb://{host}:{port}/"

# Создание клиента MongoDB
client = pymongo.MongoClient(connection_string)

db = client["memesgenbot"]
collection_memes = db["memes"]
collection_caption = db["caption_images"]
collection_users = db["users"]


API_TOKEN = "6283844380:AAFMTeiqO_s51XSndUBVMAXTZxj1xUb0TYA"
