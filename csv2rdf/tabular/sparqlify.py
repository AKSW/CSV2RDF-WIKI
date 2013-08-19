import os

import subprocess
import threading
import Queue
import time
import json
import logging

import csv2rdf.config
import csv2rdf.database
import csv2rdf.tabular.mapping
import csv2rdf.tabular.tabularfile


class Sparqlify():
    def __init__(self, resource_id):
        self.resource_id = resource_id
    
    def transform_resource_to_rdf(self, mapping_name, resource_id = None):
        if(not resource_id):
            resource_id = self.resource_id
                
        tabular_file = csv2rdf.tabular.tabularfile.TabularFile(resource_id)
        if(tabular_file.get_csv_file_path()):
            file_path = tabular_file.get_csv_file_path()
        else:
            file_path = tabular_file.download()

        mapping = csv2rdf.tabular.mapping.Mapping(resource_id)
        mapping.init()
        mapping_path = mapping.get_mapping_path(mapping_name)
        mapping_current = mapping.get_mapping_by_name(mapping_name)

        #process file based on the mapping_current options
        processed_file = mapping.process_file(file_path, mapping_current)
        file_path = str(processed_file.name)
        delimiter = mapping_current['delimiter']
        
        sparqlify_call = ["java",
                          "-cp", csv2rdf.config.config.sparqlify_jar_path,
                          "org.aksw.sparqlify.csv.CsvMapperCliMain",
                          "-f", file_path,
                          "-c", mapping_path,
                          "-s", delimiter,
                          "-h"]
        # -h - header omit
        # -d - delimiter ("")
        # -s - separator (@,;)
        # for your strange file with all the @, you could try: -s @ -d \0 -e \1 (\0 \1 - binary 0 and 1)
        # \123 or hex e.g. 0xface if you need
        
        logging.info(str(' '.join(sparqlify_call)))

        rdf_file = os.path.join(csv2rdf.config.config.rdf_files_path, str(self.resource_id) + '_' + str(mapping_name) + '.rdf')
        open(rdf_file, 'a').close() 
        f = open(rdf_file, 'w')
        process = subprocess.Popen(sparqlify_call, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #sparqlify_message = process.stderr.read()
        sparqlify_message = ""
        logging.info("rdf_file: %s" % rdf_file)

        stdout_queue = Queue.Queue()
        stdout_reader = AsynchronousFileReader(process.stdout, stdout_queue)
        stdout_reader.start()
        stderr_queue = Queue.Queue()
        stderr_reader = AsynchronousFileReader(process.stderr, stderr_queue)
        stderr_reader.start()

        stdout_size = 0

        while not stdout_reader.eof() or not stderr_reader.eof():
            # Show what we received from standard output.
            while not stdout_queue.empty():
                stdout_size += 1
                line = stdout_queue.get()
                f.write(line)
                if(stdout_size % 1000 == 0):
                    logging.info("Processed %d lines of %s" % (stdout_size, rdf_file))
                    

            # Show what we received from standard error.
            while not stderr_queue.empty():
                line = stderr_queue.get()
                logging.info('Received line on standard error: ' + repr(line))

            # Sleep a bit before asking the readers again.
            time.sleep(.1)

        # Let's be tidy and join the threads we've started.
        stdout_reader.join()
        stderr_reader.join()

        # Close subprocess' file descriptors.
        process.stdout.close()
        process.stderr.close()
        f.close()
        
        #update metadata
        mapping.update_metadata()
        
        return sparqlify_message, process.returncode
    
    def get_rdf_file_path(self, mapping_name, resource_id = None):
        if(not resource_id):
            resource_id = self.resource_id
        
        filename = resource_id + '_' + mapping_name + '.rdf'
        db = csv2rdf.database.DatabasePlainFiles(csv2rdf.config.config.rdf_files_path)
        if(db.is_exists(filename)):
            return db.get_path_to_file(filename)
        else:
            return False
        
    def get_rdf_file_url(self, configuration_name, resource_id=None):
        if(not resource_id):
            resource_id = self.resource_id
        file_path = self.get_rdf_file_path(configuration_name, resource_id=resource_id)
        if(file_path):
            return os.path.join(csv2rdf.config.config.server_base_url, self.get_rdf_file_path(configuration_name))
        else:
            return False

    def get_sparqlified_list(self):
        return os.listdir(csv2rdf.config.config.rdf_files_exposed_path)

    def update_exposed_rdf_list(self):
        db = csv2rdf.database.DatabasePlainFiles(csv2rdf.config.config.root_path)
        db.saveDbaseRaw('get_exposed_rdf_list', json.dumps(self.get_sparqlified_list()))

class AsynchronousFileReader(threading.Thread):
    '''
    Helper class to implement asynchronous reading of a file
    in a separate thread. Pushes read lines on a queue to
    be consumed in another thread.
    '''

    def __init__(self, fd, queue):
        assert isinstance(queue, Queue.Queue)
        assert callable(fd.readline)
        threading.Thread.__init__(self)
        self._fd = fd
        self._queue = queue

    def run(self):
        '''The body of the tread: read lines and put them on the queue.'''
        for line in iter(self._fd.readline, ''):
            self._queue.put(line)

    def eof(self):
        '''Check whether there is no more content to expect.'''
        return not self.is_alive() and self._queue.empty()

if __name__ == '__main__':
    sparqlify = Sparqlify('1aa9c015-3c65-4385-8d34-60ca0a875728')
    print sparqlify.transform_resource_to_rdf('default-tranformation-configuration')
    #print sparqlify.get_rdf_file_path('default-tranformation-configuration')
    #print sparqlify.get_rdf_file_url('default-tranformation-configuration')
