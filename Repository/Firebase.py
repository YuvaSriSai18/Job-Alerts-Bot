import firebase_admin
from firebase_admin import firestore, credentials
from dotenv import load_dotenv
import os

load_dotenv()

class Firebase:
    def __init__(self):
        cred = credentials.Certificate(r"utils\service_account.json")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()
    
    def add_document(self, folder_name, data):
        doc_ref = self.db.collection(folder_name).document()
        doc_ref.set(data)
        return doc_ref.id
    
    def set_document(self, folder_name, doc_id, data):
        self.db.collection(folder_name).document(doc_id).set(data)
        return doc_id
    
    def update_document(self, folder_name, doc_id, data):
        self.db.collection(folder_name).document(doc_id).update(data)
        return True
    
    def get_document(self, folder_name, doc_id):
        doc = self.db.collection(folder_name).document(doc_id).get()
        if doc.exists:
            return {"id": doc_id, **doc.to_dict()}
        return None
    
    def get_all_documents(self, folder_name):
        docs = self.db.collection(folder_name).stream()
        result = []
        for doc in docs:
            result.append({"id": doc.id, **doc.to_dict()})
        return result
    
    def delete_document(self, folder_name, doc_id):
        self.db.collection(folder_name).document(doc_id).delete()
        return True
    
    def query_by_field(self, folder_name, field_name, value):
        docs = self.db.collection(folder_name).where(field_name, "==", value).stream()
        result = []
        for doc in docs:
            result.append({"id": doc.id, **doc.to_dict()})
        return result
    
    def exists(self, folder_name, field_name, value):
        docs = self.db.collection(folder_name).where(field_name, "==", value).stream()
        for doc in docs:
            if doc.exists:
                return True
        return False
    
"""
Docstring for Repository.Firebase
| Function Name       | Purpose                                  | Example Use                           |
| ------------------- | ---------------------------------------- | ------------------------------------- |
| `addDocument()`     | Add doc with auto-generated ID           | Add new course, vehicle, etc.         |
| `setDocument()`     | Add or overwrite doc with custom ID      | Create faculty with UID as ID         |
| `updateDocument()`  | Update fields in an existing doc         | Update asset condition                |
| `getDocument()`     | Fetch single doc by ID (returns id+data) | Get details of a specific route       |
| `getAllDocuments()` | Fetch all docs in a collection           | List all hostel rooms                 |
| `deleteDocument()`  | Delete doc by ID                         | Remove a book record                  |
| `queryByField()`    | Fetch docs where a field matches a value | Get all buses assigned to route "R12" |

"""