import os
import re
import logging
from copy import copy

import urllib
import wikitools
from unidecode import unidecode
import tempfile

import csv2rdf.config
import csv2rdf.database
import csv2rdf.ckan.package
import csv2rdf.prefixcc
import csv2rdf.ckan.resource
import csv2rdf.tabular.tabularfile
import csv2rdf.interfaces

import csv2rdf.tabular.sparqlify

class Mapping(csv2rdf.interfaces.AuxilaryInterface):
    def __init__(self, resource_id = None):
        self.resource_id = resource_id
        self.wiki_site = wikitools.Wiki(csv2rdf.config.config.wiki_api_url)
        self.wiki_site.login(csv2rdf.config.config.wiki_username, password=csv2rdf.config.config.wiki_password)

    def update_mapping(self, header, class_, mappingName):
        self.init_mappings_only()
        mapping = self.get_mapping_by_name(mappingName)
        new_mapping = copy(mapping)
        new_mapping['class'] = class_['value']
        for num, item in enumerate(header):
            key = "col" + str(num + 1)
            if(item['uri'] == ''):
                new_mapping[key] = item['label']
            else:
                new_mapping[key] = item['uri']

            if('datatype' in item and item['datatype'] != ''):
                new_mapping[key] = "%s^^%s"%(new_mapping[key], item['datatype']['uri']) 

        wikified_mapping = self.convert_mapping_to_wiki_template(new_mapping)
        #delete mapping
        mapping_start = self.mappings_start[mappingName]
        mapping_end = self.mappings_end[mappingName]
        self.delete_template_from_wiki_page(mapping_start, mapping_end)
        self.add_mapping_to_wiki_page(wikified_mapping)
        self.wiki_page = self.remove_blank_lines_from_wiki_page(self.wiki_page)
        self.create_wiki_page(self.wiki_page)
        self.updateMetadata(self.resourceId, mappingName)
        #fire_up the conversion process for this mapping
        sparqlify = csv2rdf.tabular.sparqlify.Sparqlify(self.resource_id)
        sparqlify.addResourceToProcessingQueue(mappingName)

    def init_mappings_only(self):
        self.wiki_page = self.request_wiki_page()
        if(self.wiki_page):
            self.metadata = self.extract_metadata_from_wiki_page(self.wiki_page)
            (self.mappings, self.mappings_start, self.mappings_end) = self.extract_mappings_from_wiki_page(self.wiki_page)
            self.wiki_page = self.remove_blank_lines_from_wiki_page(self.wiki_page)
            self.mappings = self.process_mappings(self.mappings)
            return True
        else:
            return self.wiki_page
    
    def init(self):
        self.init_mappings_only()
        self.save_csv_mappings(self.mappings)

    def process_mappings(self, mappings):
        for mapping in mappings:
            mapping['omitRows'] = self.process_omitRows(mapping['omitRows']) if mapping['omitRows'] != '-1' else [-1]
            mapping['omitCols'] = self.process_omitCols(mapping['omitCols']) if mapping['omitCols'] != '-1' else [-1]
            mapping['header'] = self.process_header(mapping['header']) if mapping['header'] != '-1' else [1]
            mapping['delimiter'] = mapping['delimiter'] if ('delimiter' in mapping) else ','
        return mappings

    def update_csv2rdf_wiki_page_list(self):
        params = {
                  'action':'query', 
                  'list':'allpages', 
                  'apnamespace':'505' #505 - csv2rdf namespace
                 }
        request = wikitools.APIRequest(self.wiki_site, params)
        result = request.query()
        db = csv2rdf.database.DatabasePlainFiles(csv2rdf.config.config.data_path)
        db.saveDbase(csv2rdf.config.config.data_all_csv2rdf_pages, result)

    def get_csv2rdf_wiki_page_list(self):
        db = csv2rdf.database.DatabasePlainFiles(csv2rdf.config.config.data_path)
        return db.loadDbase(csv2rdf.config.config.data_all_csv2rdf_pages)

    def get_all_csv2rdf_page_ids(self):
        """
            Returns the list of all wiki page ids
        """
        page_list = self.get_csv2rdf_wiki_page_list()
        titles = []
        for page in page_list['query']['allpages']:
            titles.append( page['title'][8:].lower() )
        return titles

    def request_wiki_page(self, resource_id = None):
        """
            Get a wiki page
            From the Mapping Wiki
        """
        if(not resource_id):
            resource_id = self.resource_id
        
        title = csv2rdf.config.config.wiki_csv2rdf_namespace + resource_id
        params = {'action':'query', 'prop':'revisions', 'rvprop':'content', 'titles':title}
        request = wikitools.APIRequest(self.wiki_site, params)
        result = request.query()
        pages = result['query']['pages']
        try:
            for pageid in pages:
                page = pages[pageid]
                #get the last revision
                return page['revisions'][0]["*"]
        except:
            return False
    
    def extract_metadata_from_wiki_page(self, wiki_page):
        (templates, template_start, template_end) = self.parse_template(wiki_page, 'CSV2RDFMetadata')
        try:
            self.delete_template_from_wiki_page(template_start['CSV2RDFMetadata'], template_end['CSV2RDFMetadata'])
        except BaseException as e:
            print str(e)
        if(len(templates) != 0):
            return templates[0]
        else:
            return {}

    def extract_mappings_from_wiki_page(self, wiki_page):        
        (templates, template_start, template_end) = self.parse_template(wiki_page, 'RelCSV2RDF')
        #self.delete_template_from_wiki_page(template_start, template_end)
        return (templates, template_start, template_end)

    def parse_template(self, wiki_page, template_name):
        lines = wiki_page.split('\n')
        templates = []
        inside_template = False        
        template_start = {}
        template_end = {}
        template_start_one = 0
        template_end_one = 0
        for num, line in enumerate(lines):
            if(re.match('^{{'+template_name, line)):
                inside_template = True
                template = {}
                template_start_one = num
                template['type'] = line[2:] #'RelCSV2RDF|'
                template['type'] = template['type'][:-1] # 'RelCSV2RDF'
                continue
            
            if(inside_template and re.match('^}}', line)):
                template_end_one = num
                #print template

                if(template['type'].startswith('RelCSV2RDF')):
                    if(not template['name'] in template_start):
                        template_start[template['name']] = []

                    if(not template['name'] in template_end):
                        template_end[template['name']] = []
                    template_end[template['name']] = [template_end_one]

                    template_start[template['name']] = [template_start_one]

                else:
                    if(not template_name in template_start):
                        template_start[template_name] = []

                    if(not template_name in template_end):
                        template_end[template_name] = []

                    template_start[template_name].append(template_start_one)
                    template_end[template_name].append(template_end_one)

                #push mapping to the mappings
                templates.append(template)
                del template
                inside_template = False

                continue
            
            if(inside_template):
                if(len(line.split('=')) < 2):
                    continue
                    #line = lines[num-1] + lines[num]
                prop = line.split('=')[0]
                value = str(line.split('=')[1].encode('utf-8'))
                prop = prop.strip()
                #Encode value to URL
                value = value[:-1]
                value = value.strip()
                if not prop == 'delimiter':
                    value = urllib.quote(value)
                template[prop] = value

        return (templates, template_start, template_end)

    def delete_template_from_wiki_page(self, template_start, template_end, template_name=None):
        lines = self.wiki_page.split('\n')
        for i in range(0, len(template_start)):
            for j in range(template_start[i], template_end[i] + 1):
                lines[j] = ''

        self.wiki_page = '\n'.join(lines)
    
    def remove_blank_lines_from_wiki_page(self, wiki_page):
        lines = wiki_page.split('\n')
        output = []
        for num, line in enumerate(lines):
            if(not line == ''):
                output.append(line)
        return '\n'.join(output)

    def convert_mapping_to_wiki_template(self, mapping, resource_id = None):
        if(not resource_id):
            resource_id = self.resource_id

        result_mapping = mapping.copy()
        result_mapping['class'] = str(mapping['class'])
        result_mapping['header'] = str(mapping['header'])[1:-1]
        result_mapping['omitCols'] = str(mapping['omitCols'])[1:-1]
        result_mapping['omitRows'] = str(mapping['omitRows'])[1:-1]
        del(result_mapping['type'])
        #'header': [1], u'omitCols': [-1], u'col10': 'rdfs%3Acomment', 'delimiter': ',', u'omitRows': [-1], 'type': u'RelCSV2RDF'
        wiki_template = "{{RelCSV2RDF| \n"
        for item in result_mapping:
            wiki_template += "%s = %s |\n" % (item, urllib.unquote(result_mapping[item]))
        wiki_template += "}}"
        return wiki_template

    def convert_mapping_to_sparqlifyml(self, mapping, resource_id = None):
        if(not resource_id):
            resource_id = self.resource_id
        
        csv2rdf_mapping = ''
        prefixcc = csv2rdf.prefixcc.PrefixCC()
        #scan all colX values and extract prefixes
        prefixes = set()
        properties = {} #properties['col1'] = id >>>> ?obs myprefix:id ?col1
        for key in mapping.keys():
            if(re.match('^col', key)):
                prefixes = set(list(prefixes) + list(prefixcc.extract_prefixes(mapping[key])))
                properties[key] = mapping[key]
        prefixes = list(prefixes)
        #delete omitCols from the properties array and rearrange it
        for key in properties.keys():
            if(int(key[3:]) in mapping['omitCols']):
                del properties[key]
        #remove duplicates from prefixes
        prefixes = dict.fromkeys(prefixes).keys()
        #inject qb prefix
        #prefixes += ['qb']
        for prefix in prefixes:
            csv2rdf_mapping += prefixcc.get_sparqlify_namespace(prefix) + "\n"
        #Add custom prefix to non-prefixed values
        csv2rdf_mapping += "Prefix publicdata:<http://wiki.publicdata.eu/ontology/>" + "\n"
        #Add fn sparqlify prefix
        csv2rdf_mapping += "Prefix fn:<http://aksw.org/sparqlify/>" + "\n"
        
        csv2rdf_mapping += "Create View Template DefaultView As" + "\n"
        csv2rdf_mapping += "  CONSTRUCT {" + "\n"
        #csv2rdfconfig += "      ?obs a qb:Observation ." + "\n"
        
        for prop in properties:
            csv2rdf_mapping += "      ?obs "+ self._extract_property(properties[prop]) +" ?"+ prop + " .\n"
        csv2rdf_mapping += "  }" + "\n"
        csv2rdf_mapping += "  With" + "\n"
        csv2rdf_mapping += "      ?obs = uri(concat('http://data.publicdata.eu/"+resource_id+"/', ?rowId))" + "\n"
        for prop in properties:
            csv2rdf_mapping += "      ?" + prop + " = " + self._extract_type(properties[prop], prop) + "\n"

        return csv2rdf_mapping
    
    def _extract_property(self, prop):
        """
            Auxilary method for tabular to spaqrlify-ml convertion
        """
        prop = prop.split('%5E%5E')[0]
        
        if(len(prop.split('%3A')) == 1): # %3A = :
            return "<http://wiki.publicdata.eu/ontology/"+str(prop)+">"
        else:
            return "<" + ':'.join(prop.split('%3A')) + ">"
    
    def _extract_type(self, wikiString, column):
        """
            Auxilary method for tabular to spaqrlify-ml convertion
        """
        column_number = column[3:]
        try:
            t = wikiString.split('%5E%5E')[1]
            #t = t.split('^^')[0]
            t = ':'.join(t.split('%3A')) 
            t = urllib.unquote(t)
            return "typedLiteral(?"+column_number+", \""+t+"\")"
        except:
            return "plainLiteral(?"+column_number+")"
        
    def save_csv_mappings(self, mappings, resource_id = None):
        if(not resource_id):
            resource_id = self.resource_id
            
        db = csv2rdf.database.DatabasePlainFiles(csv2rdf.config.config.sparqlify_mappings_path)
        for mapping in mappings:
            sparqlifyml = self.convert_mapping_to_sparqlifyml(mapping, resource_id=resource_id)
            filename = resource_id + '_' + mapping['name'] + '.sparqlify'
            db.saveDbaseRaw(filename, sparqlifyml)
    
    def create_wiki_page(self, text, resource_id = None):
        """
            Replace the whole resource page with the text
            User should be acknowledged bot!
        """
        if(not resource_id):
            resource_id = self.resource_id

        if(not type(text) is str):
            text = unidecode(text)#.encode('utf-8')
        title = csv2rdf.config.config.wiki_csv2rdf_namespace + resource_id
        page = wikitools.Page(self.wiki_site, title=title)
        result = page.edit(text=text, bot=True)
        return result

    def delete_wiki_page(self, resource_id = None):
        if(not resource_id):
            resource_id = self.resource_id

        title = csv2rdf.config.config.wiki_csv2rdf_namespace + resource_id
        try:
            page = wikitools.Page(self.wiki_site, title=title)
            result = page.delete()
            return result
        except BaseException as e:
            logging.info("An exception occured, while deleting wiki page %s" % str(e))
    
    def generate_default_wiki_page(self, resource_id = None):
        """
        """
        if(not resource_id):
            resource_id = self.resource_id
        
        resource = csv2rdf.ckan.resource.Resource(resource_id)
        resource.init()
        package = csv2rdf.ckan.package.Package(resource.package_name)
        tabular_file = csv2rdf.tabular.tabularfile.TabularFile(resource_id)
        
        page = '{{CSV2RDFHeader}} \n'
        page += '\n'
        
        #link to the publicdata.eu dataset
        page += '{{CSV2RDFResourceLink | \n'
        page += 'packageId = '+package.name+' | \n'
        page += 'packageName = "'+package.title+'" | \n'
        page += 'resourceId = '+resource.id+' | \n'
        page += 'resourceName = "'+resource.description+'" | \n'
        page += '}} \n'
        page += '\n'
        
        #get the header from the csv file
        
        header_position = tabular_file.get_header_position()
        header = tabular_file.extract_header(header_position)
        
        #CSV2RDF Template
        page += '{{RelCSV2RDF|\n'
        page += 'name = default-tranformation-configuration |\n'
        page += 'header = '+str(header_position)+' |\n'
        page += 'omitRows = -1 |\n'
        page += 'omitCols = -1 |\n'
        
        #Split header and create column definition
        for num, item in enumerate(header):
            #if(not type(item) is str):
            item = unidecode(item)
            page += 'col'+str(num+1)+' = '+item.rstrip()+' |\n'
            if(num > 500): # too many columns in this csv OR bad format
                break
        
        #Close template
        page += '}}\n'
        page += '\n'
        
        page = page.encode('utf-8')
                
        return page

    def updateMetadata(self, resourceId, mappingName):
        self.update_metadata_csv_filesize(resourceId)
        self.update_metadata_csv_number_of_lines(resourceId)
        self.update_metadata_csv_number_of_columns(mappingName)
        self.update_metadata_rdf_number_of_triples(mappingName)
        self.update_metadata_rdf_last_sparqlified(mappingName)
        self.add_metadata_to_wiki_page()
        self.create_wiki_page(self.wiki_page)
        
    def update_metadata_csv_filesize(self, resourceId):
        tabular_file = csv2rdf.tabular.tabularfile.TabularFile(resourceId) 
        csv_filesize = tabular_file.get_csv_filesize()
        self.metadata['filesize'] = str(csv_filesize)

    def update_metadata_csv_number_of_lines(self, resourceId):
        tabular_file = csv2rdf.tabular.tabularfile.TabularFile(resourceId)
        csv_number_of_lines = tabular_file.get_csv_number_of_lines()
        self.metadata['csv_number_of_lines'] = str(csv_number_of_lines)

    def update_metadata_csv_number_of_columns(self, mappingName):
        cols = 0
        currentMapping = self.get_mapping_by_name(mappingName)
        for key in currentMapping.keys():
            if(re.match("^col.*", key)):
                cols += 1
        self.metadata['csv_number_of_columns'] = str(cols)

    def update_metadata_rdf_number_of_triples(self, mappingName):
        """
            using the default mapping here (mapping 0)
        """
        rdf_filename = self.resource_id + "_" + mappingName + ".rdf"
        db = csv2rdf.database.DatabasePlainFiles(csv2rdf.config.config.rdf_files_path)
        rdf_number_of_triples = db.count_line_number(rdf_filename)
        self.metadata['rdf_number_of_triples'] = str(rdf_number_of_triples)

    def update_metadata_rdf_last_sparqlified(self, mappingName):
        rdf_filename = self.resource_id + "_" + mappingName + ".rdf"
        db = csv2rdf.database.DatabasePlainFiles(csv2rdf.config.config.rdf_files_path)
        rdf_last_sparqlified = db.get_last_access_time(rdf_filename)
        self.metadata['rdf_last_sparqlified'] = str(rdf_last_sparqlified)

    def add_metadata_to_wiki_page(self):
        metadata = self.metadata
        lines = self.wiki_page.split('\n')
        lines.append("{{CSV2RDFMetadata|")
        for key in metadata.keys():
            lines.append(key +"="+metadata[key]+" |")
        lines.append("}}")
        self.wiki_page = '\n'.join(lines)

    def add_mapping_to_wiki_page(self, mapping):
        lines = self.wiki_page.split('\n')
        lines.append(mapping)
        self.wiki_page = '\n'.join(lines)
        
    def process_omitRows(self, string):
        output = []
        ranges = string.split('%2C')
        for r in ranges:
            if(len(r.split('-')) < 2):
                output.append(int(r))
            else:
                start = int(r.split('-')[0])
                end = int(r.split('-')[1])
                list = range(start, end + 1)
                output = output + list
        return output

    def process_omitCols(self, string):
        return self.process_omitRows(string)

    def process_header(self, string):
        return self.process_omitRows(string)

    def process_file(self, original_file_path, mapping_current):
        omitRows = mapping_current['omitRows']

        try:
            processed_file = tempfile.NamedTemporaryFile(delete=False)
            original_file = open(original_file_path, 'rU')
            for line_num, line in enumerate(original_file.readlines()):
                #line_num = 0 is a header, we do not process it
                if(not line_num in omitRows):
                    processed_file.write(line)
            original_file.close()
            processed_file.close()
        except BaseException as e:
            logging.warning("An exception occured: %s" % str(e))

        return processed_file

    def get_mapping_path(self, configuration_name, resource_id=None):
        if(not resource_id):
            resource_id = self.resource_id
        file_path = os.path.join(csv2rdf.config.config.sparqlify_mappings_path, str(resource_id) + '_' + str(configuration_name) + '.sparqlify')
        if(os.path.exists(file_path)):
            return file_path
        else:
            return False
    
    def get_mapping_url(self, configuration_name, resource_id = None):
        if(not resource_id):
            resource_id = self.resource_id
        file_path = self.get_mapping_path(configuration_name, resource_id=resource_id)
        if(file_path):
            return os.path.join(csv2rdf.config.config.server_base_url, self.get_mapping_path(configuration_name, resource_id=resource_id))
        else:
            return False
        
    def get_mapping_names(self):
        names = []
        for mapping in self.mappings:
            names.append(mapping['name'])
        return names
    
    def get_mapping_by_name(self, mapping_name):
        return self.get_by_name(mapping_name, self.mappings)

    def get_by_name(self, mapping_name, mappings):
        for mapping in mappings:
            if(mapping['name'] == mapping_name):
                return mapping
        return False

    def get_outdated_and_new_wiki_pages(self):
        logging.info("Looking for outdated and new wiki pages ... Started.")
        tf = csv2rdf.tabular.tabularfile.TabularFile('')
        resources_ids = tf.get_csv_resource_list_local()

        page_ids_list = self.get_all_csv2rdf_page_ids()
        pages_outdated = []
        pages_new = [] 

        for page_id in page_ids_list:
            if(not page_id in resources_ids):
                pages_outdated.append(page_id) 

        for resource_id in resources_ids:
            if(not resource_id in page_ids_list):
                pages_new.append(resource_id)

        logging.info("Looking for outdated and new wiki pages ... Complete.")
        return (pages_outdated, pages_new)

    def get_mapping_headers(self):
        if(not hasattr(self, 'mappings')):
            self.init_mappings_only()
        headers = []
        for mapping in self.mappings:
            header = {mapping['name']: []}
            for item in mapping:
                if(item.startswith("col")):
                    header[mapping['name']].append((int(item[3:]), urllib.unquote(mapping[item])))
            header[mapping['name']].sort()
            headers.append(header)
        return headers

    def get_header_by_name(self, mapping_name):
        headers = self.get_mapping_headers()
        for header in headers:
            if(mapping_name in header.keys()):
                return header

    def create_default_wiki_page(self, resource_id=None):
        default_wiki_page = self.generate_default_wiki_page(resource_id)
        self.create_wiki_page(default_wiki_page, resource_id)
    
if __name__ == '__main__':
    #Test #1 update metadata
    testResourceId = "02f31d80-40cc-496d-ad79-2cf02daa5675"
    testMappingName = "csv2rdf-interface-generated"
    mapping = Mapping(testResourceId)
    mapping.init_mappings_only()
    mapping.updateMetadata(testResourceId, testMappingName)
