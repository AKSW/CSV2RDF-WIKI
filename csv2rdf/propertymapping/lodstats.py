import requests
import json

from csv2rdf.propertymapping.mapper import Mapper

class LodstatsMapper(Mapper):
    def __init__(self):
        pass

    def getMappings(self, resourceId):
        headers = self._getHeaders(resourceId)
        entities = self._getEntities(resourceId)
        payload = {'headers': json.dumps(headers), 'entities': json.dumps(entities)}
        postUri = 'http://localhost:5000/property/search'
        r = requests.post(postUri, data=payload)
        content = r.json()
        import pprint
        pprinter = pprint.PrettyPrinter()
        pprinter.pprint(content)
        #import ipdb; ipdb.set_trace()

if __name__ == "__main__":
    testResourceId = "8b51874e-cda8-4910-a3c0-9140e11164a3"
    lodstatsmapper = LodstatsMapper()
    lodstatsmapper.getMappings(testResourceId)
