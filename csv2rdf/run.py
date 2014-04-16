#
# Server interface - views here
#
import cherrypy
import json
import pystache
import logging
import os

import csv2rdf.config.config
import csv2rdf.ckan.application
import csv2rdf.ckan.resource
import csv2rdf.tabular.sparqlify
import csv2rdf.tabular.mapping
import csv2rdf.tabular.refine

# Template objects
from csv2rdf.server.pystachetempl.index import IndexTemplate
from csv2rdf.server.pystachetempl.csv2rdfTemplate import Csv2rdfTemplate
from csv2rdf.server.pystachetempl.rdfedit import RdfEditTemplate


class CSV2RDFApp(object):
    def __init__(self):
        self.renderer = pystache.Renderer(search_dirs=self.get_template_search_dirs())

    @cherrypy.expose(alias='index.html')
    def index(self):
        index = IndexTemplate()
        return self.renderer.render(index)

    def get_template_search_dirs(self):
        template_root = os.path.join(csv2rdf.config.config.root_path,
                                     "csv2rdf", "server", "static",
                                     "javascript","src")
        search_dirs = []
        for root, dirs, files in os.walk(template_root):
            search_dirs.append(root)

        return search_dirs

    @cherrypy.expose(alias='csv2rdf.html')
    def csv2rdf(self):
        #read several resource, give navigation link to wiki and CKAN
        #let transform each of them
        res1 = csv2rdf.ckan.resource.Resource('676e2f9b-c05f-4fd5-844a-25497c3c2c9e')
        res2 = csv2rdf.ckan.resource.Resource('6023100d-1c76-4bee-9429-105caa061b9f')
        res3 = csv2rdf.ckan.resource.Resource('1aa9c015-3c65-4385-8d34-60ca0a875728')
        resources = [res1, res2, res3]
        map(lambda x: x.init(), resources)
        page = Csv2rdfTemplate(resources)
        return self.renderer.render(page)

    @cherrypy.expose(alias="rdf_edit.html")
    def rdf_edit(self, resource_id, configuration_name='default-tranformation-configuration'):
        mapping_name = configuration_name
        resource_id = resource_id.lower()

        resource = csv2rdf.ckan.resource.Resource(resource_id)
        resource.init()
        sparqlify = csv2rdf.tabular.sparqlify.Sparqlify(resource_id)

        if(sparqlify.transform_resource_to_rdf(mapping_name)):
            logging.info("The resource %s %s was sent to the queue." % (resource_id, mapping_name))

            rdf_edit = RdfEditTemplate(resource, mapping_name)
            return self.renderer.render(rdf_edit)
        else:
            return self.renderer.render(rdf_edit)

    @cherrypy.expose(alias="mapping_edit_interface.html")
    def mapping_edit_interface(self,
                               resource_id,
                               configuration_name='default-tranformation-configuration'):

        mapping_name = configuration_name
        mapping_edit_interface = csv2rdf.server.pystachetempl.MappingEditInterface(resource_id, mapping_name)
        return self.renderer.render(mapping_edit_interface)


    ####### AJAX calls

    @cherrypy.expose
    def getSparqlifiedResourceNLines(self, entityName, resourceId, n):
        n = int(n)
        rdfoutputpath = 'sparqlified/'+entityName+'/'
        rdfoutput = rdfoutputpath+resourceId+'.rdf'
        print rdfoutput
        try:
            with open(rdfoutput, 'r') as rdffile:
                head=[rdffile.next() for x in xrange(n)]
            return json.dumps(head)
        except:
            return json.dumps('')

    @cherrypy.expose
    def getUriByCkanResourceId(self, resource_id):
        resource = csv2rdf.ckan.resource.Resource(resource_id)
        resource.init()
        return json.dumps(resource.url)

    @cherrypy.expose
    def get_exposed_rdf_list(self):
        ckan = csv2rdf.ckan.application.CkanApplication()
        return json.dumps(ckan.get_sparqlified_list())

    def _get_black_list(self):
        f = open('files_over_50MB', 'rU')
        black_list = f.read()
        f.close()
        return black_list.split('\n')


    ####### Metadata export
    @cherrypy.expose
    def getResourceMetadata(self, resourceId):
        resource = csv2rdf.ckan.resource.Resource(resourceId)
        resource.init()
        return resource.get_metadata()

class CSV2RDFRefineAPI(object):
    ####### csv2rdf-interface (ember): AJAX calls
    @cherrypy.expose(alias="refines")
    def getDataForRefine(self, resourceId):
        cherrypy.response.headers['Access-Control-Allow-Origin'] = "*"
        refine = csv2rdf.tabular.refine.Refine(resourceId)
        return refine.get_data_json()

    @cherrypy.expose(alias="tables")
    def getDataTable(self, resourceId):
        cherrypy.response.headers['Access-Control-Allow-Origin'] = "*"
        refine = csv2rdf.tabular.refine.Refine(resourceId)
        return refine.get_csv_table_json()

    @cherrypy.expose(alias="mappings")
    def getDataMappings(self, resourceId):
        cherrypy.response.headers['Access-Control-Allow-Origin'] = "*"
        refine = csv2rdf.tabular.refine.Refine(resourceId)
        return refine.get_mappings_json()

    @cherrypy.expose(alias="resources")
    def getDataResource(self, resourceId):
        cherrypy.response.headers['Access-Control-Allow-Origin'] = "*"
        refine = csv2rdf.tabular.refine.Refine(resourceId)
        return refine.get_resource_json()

class TransformAPI(object):

    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Access-Control-Allow-Origin'] = "*"
        cl = cherrypy.request.headers['Content-Length']
        rawbody = cherrypy.request.body.read(int(cl))
        table = json.loads(rawbody)
        sparqlify = csv2rdf.tabular.sparqlify.Sparqlify('')
        sparqlify.process_table_from_json(table)
        return "In a queue now!"


if __name__ == '__main__':
    publicdataeu = CSV2RDFApp()
    cherrypy.quickstart(publicdataeu, '/', 'server/config')
    cherrypy.config.update('server/config')

def application(environ, start_response):
    cherrypy.tree.mount(CSV2RDFApp(), '/', 'csv2rdf/server/config')
    cherrypy.tree.mount(CSV2RDFRefineAPI(), '/api/', 'csv2rdf/server/config')
    cherrypy.tree.mount(TransformAPI(), '/api/transform/', 'csv2rdf/server/config')
    return cherrypy.tree(environ, start_response)
