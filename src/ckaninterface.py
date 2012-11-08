#s
# Logic for fetching and processing CKAN data
#
import ckanclient
from database import Database
import os
import ckanconfig
import requests
import json
requests.defaults.danger_mode = True

class CkanInterface:
    def __init__(self, base_location=ckanconfig.base_location, api_key=ckanconfig.api_key):
        self.base_location = base_location
        self.api_key = api_key
        self.ckan = ckanclient.CkanClient(base_location=base_location,
                                          api_key=api_key)
        self.db = Database('data/')
        self.errorlog = open('error.log', 'wb')
        self.log = open('log.log', 'wb')
        
    def getEntity(self, entityName):
        try:
            entity = self.db.loadDbase(entityName)
        except IOError as error:
            print "I/O error({0}): {1}".format(error.errno, error.strerror)
            print "Creating new entity"
            entity = self.ckan.package_entity_get(entityName)
            self.db.saveDbase(entityName, entity)
        return entity
    
    def getEntityFiles(self, entityName):
        import os
        from subprocess import call
        filelist = os.listdir("files/"+entityName)
        for filename in filelist:
            print os.getcwd()
            sparqlify = "../lib/sparqlify/sparqlify.jar"
            csvfile = "files/"+entityName+"/"+filename
            print csvfile
            configfile = "sparqlify-mappings/"+entityName+" "+filename+".sparqlify"
            retcode = call(["java", "-cp", sparqlify, "org.aksw.sparqlify.csv.CsvMapperCliMain", "-f", csvfile, "-c", configfile])
            print retcode
        pass
    
    def pFormat(self, object):
        import pprint
        pp = pprint.PrettyPrinter(indent=4)
        return pp.pformat(object)
            
    def getPackageList(self):
        try:
            package_list = self.db.loadDbase("package_list")
        except IOError as error:
            print "I/O error({0}): {1}".format(error.errno, error.strerror)
            print "Creating new package list"
            package_list = self.ckan.package_register_get()
            self.db.saveDbase("package_list", package_list)
        return package_list
    
    def isCSV(self, resource):
        import re
        if(re.search( r'csv', resource['format'], re.M|re.I)):
            return True
        else:
            return False
    
    def rewriteEntity(self, entity):
        entityName = entity['name']
        newpath = 'files/'+entityName+'/'
        self.filesdb = Database(newpath)
        for resource in entity['resources']:
            url = resource['url']
            filename = url.split('/')[-1].split('#')[0].split('?')[0]
            try:
                resource = self.filesdb.loadDbase(filename)
                self.filesdb.saveDbaseRaw(filename, resource)
            except:
                pass
       
    def downloadEntityResources(self, entity):
        entityName = entity['name']
        newpath = 'files/'+entityName+'/'
        self.filesdb = Database(newpath)
        if not os.path.exists(newpath):
            os.makedirs(newpath)
        for resource in entity['resources']:
            print resource['url'].encode('utf-8')
            url = resource['url']
            filename = url.split('/')[-1].split('#')[0].split('?')[0]
            try:
                resource = self.filesdb.loadDbase(filename)
                self.log.write(entityName.encode('utf-8') + ' ' + url.encode('utf-8') + ' readed from HDD\n')
                self.log.flush()
            except IOError as error:
                print "I/O error({0}): {1}".format(error.errno, error.strerror)
                print "Creating new folder"
                print "Fetching resource from URI"
                try:
                    r = requests.get(url, timeout=10)
                    self.filesdb.saveDBaseRaw(filename, r.content)
                    self.log.write(entityName.encode('utf-8') + ' ' + url.encode('utf-8') + ' OK!\n')
                    self.log.flush()
                except Exception as e:
                    self.errorlog.write(entityName.encode('utf-8') + ' ' + url.encode('utf-8') + ' ' + str(e) + '\n')
                    self.errorlog.flush()
    
    def downloadResource(self, entityName, resourceId):
        #hack here
        resourceUrl = self.getResourceUrl(entityName, resourceId)
        
        newpath = 'files/'+entityName+'/'
        self.filesdb = Database(newpath)
        if not os.path.exists(newpath):
            os.makedirs(newpath)
        filename = self.extractFilenameFromUrl(resourceUrl)
        try:
            resource = self.filesdb.loadDbaseRaw(filename)
            return newpath + filename
        except:
            try:
                r = requests.get(resourceUrl, timeout=10)
                self.filesdb.saveDbaseRaw(filename, r.content)
                self.log.write(entityName.encode('utf-8') + ' ' + resourceUrl.encode('utf-8') + ' file downloaded OK!\n')
                self.log.flush()
                return newpath + filename
            except Exception as e:
                self.errorlog.write(entityName.encode('utf-8') + ' ' + resourceUrl.encode('utf-8') + ' ' + str(e) + '\n')
                self.errorlog.flush()
                return False
    
    def extractFilenameFromUrl(self, resourceUrl):
        return resourceUrl.split('/')[-1].split('#')[0].split('?')[0]
            
    def getResourceId(self, entityName, resourceUrl):
        entity = self.getEntity(entityName)
        for resource in entity['resources']:
            if(resource['url'] == resourceUrl):
                return resource['id']
    
    def getResourceUrl(self, entityName, resourceId):
        entity = self.getEntity(entityName)
        for resource in entity['resources']:
            if(resource['id'] == resourceId):
                return resource['url']
                
    def getResourceKey(self, entityName, resourceId, key):
        entity = self.getEntity(entityName)
        for resource in entity['resources']:
            if(resource['id'] == resourceId):
                return resource[key]
                
    def getResourceById(self, resourceId):
        data = json.dumps({'id': resourceId})
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        url = 'http://publicdata.eu/api/action/resource_show'
        r = requests.post(url, timeout=10, data=data, headers=headers)
        resource = json.loads(r.content)
        resource = resource["result"]
        return resource
    
    def getResourcePackage(self, resourceId):
        resource = self.getResourceById(resourceId)
        url = 'http://publicdata.eu/api/rest/revision/' + resource['revision_id']
        r = requests.get(url, timeout=10)
        revision = json.loads(r.content)
        return revision["packages"][0]
    
    def getCSVResourceList(self):
        output = []
        package_list = ckan.getPackageList()
                
        db = Database('')
        return db.loadDbase('csvResourceIdList')
    
    def updateCSVResourceList(self):
        output = []
        package_list = ckan.getPackageList()
                
        for package in package_list:
            entity = self.getEntity(package)
            for resource in entity['resources']:
                if(self.isCSV(resource)):
                    output.append(resource['id'])
        
        db = Database('')
        db.saveDbase('csvResourceIdList', output)
        
    def createDefaultPageForAllCSV(self):
        from wikitoolsinterface import WikiToolsInterface
        wt = WikiToolsInterface()
        csvResources = self.getCSVResourceList()
        for resourceId in csvResources:
            text = wt.generateDefaultPageForResource(resourceId)
            wt.createPage(resourceId, text)

# 
# For execution time measure:
# import time
# start_time = time.time()
# function()
# print time.time() - start_time, "seconds"
# 
            
if __name__ == '__main__':
    #Test area				
    #getting package list
    ckan = CkanInterface(base_location='http://publicdata.eu/api', api_key='e7a928be-a3e8-4a34-b25e-ef641045bbaf')
    package_list = ckan.getPackageList()
    
    #create a list of csv resources (?)
    #ckan.updateCSVResourceList()
    #csvResources = ckan.getCSVResourceList()
    #print len(csvResources)
    #CSV: 12224
    #Overall: 55846
    