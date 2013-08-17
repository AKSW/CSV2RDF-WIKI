import os
import re
import subprocess
import logging

import csv
import requests
from magic import Magic

from config import config
from database import DatabasePlainFiles
from ckan.resource import Resource


class TabularFile():
    def __init__(self, resource_id):
        self.id = resource_id
        self.filename = self.id
    
    def download(self):
        resource = Resource(self.id)
        resource.init()
        try:
            r = requests.get(resource.url, timeout=config.ckan_request_timeout)
            assert r.ok, r
            file = DatabasePlainFiles(config.resources_path)
            file.saveDbaseRaw(self.filename, r.content)
            logging.info("File %s downloaded and saved successfully" % self.id)
            return self.get_csv_file_path()
        except BaseException as e:
            logging.warning("Could not download the resource %s " % str(self.id))
            logging.warning("Exception occured: %s" % str(e))
            return False

    def get_csv_filesize(self):
        filepath = self.get_csv_file_path()
        return os.path.getsize(filepath)

    def get_csv_number_of_lines(self):
        db = DatabasePlainFiles(config.resources_path)
        return db.count_line_number(self.filename)

    def delete(self):
        db = DatabasePlainFiles(config.resources_path)
        db.delete(self.filename)
        return True
        
    def get_csv_file_path(self):
        db = DatabasePlainFiles(config.resources_path)
        if(db.is_exists(self.filename)):
            return db.get_path_to_file(self.filename)
        else:
            return False
        
    def get_csv_file_url(self):
        file_path = self.get_csv_file_path()
        if(file_path):
            return os.path.join(config.server_base_url, file_path)
        else:
            return False
    
    def read_resource_file(self):
        try:
            file = DatabasePlainFiles(config.resources_path)
            return file.loadDbaseRaw(self.filename)
        except BaseException as e:
            print "Could not read the resource! " + str(e)
            return False
    
    def get_header_position(self):
        """
            Stub for the header recognition problem!
        """
        return 1
    
    def extract_header(self, position):
        """
            This function take the first line of the csv file
            as a header. Should work in 60% of all cases.
        """
        db = DatabasePlainFiles(config.resources_path)
        with open(db.get_path_to_file(self.filename), 'rU') as csvfile:
            reader = csv.reader(csvfile)
            try:
                for num, row in enumerate(reader, 1):
                    if(num == position):
                        return row
            except BaseException as e:
                print str(e)
                return []
    
    def validate(self):
        filename = self.filename
        (encoding, info) = self.get_info_about()
        logging.debug("File encoding: %s" % encoding)
        logging.debug("File info: %s" % info)

        if(re.match('.*HTML.*', info) or
           re.match('.*[Tt]orrent.*',info) or
           self.isXML() or
           self.isHTML()):
            logging.debug("File is html, torrent or xml file ... Deleting")
            self.delete()
            return True

        if(encoding == "utf-16le"):
            #TODO: work with utf-8
            logging.debug("File is in UTF-16 encoding ... recoding to ASCII.")
            self._process_utf16(filename)
        elif(re.match("^binary", encoding) or
             re.match("^application/.*", encoding)):
            self._process_based_on(info, filename)
        else:
            return True
    
    def get_info_about(self):
        """
            return (encoding, info) tuple
            info is a plain string and has to be parsed 
        """
        db = DatabasePlainFiles(config.resources_path)
        filename = db.get_path_to_file(self.filename)
        mgc_encoding = Magic(mime=False, mime_encoding=True)
        mgc_string = Magic(mime=False, mime_encoding=False)
        encoding = mgc_encoding.from_file(filename)
        info = mgc_string.from_file(filename)
        return (encoding, info)
    
    def isHTML(self):
        db = DatabasePlainFiles(config.resources_path)
        file_chunk = db.loadDbaseChunk(self.filename)
        check_1 = ".*\<\!DOCTYPE html PUBLIC.*"
        result = False
        for line in file_chunk:
            if(re.match(check_1, line)):
                result = True
        return result

    def isXML(self):
        db = DatabasePlainFiles(config.resources_path)
        file_chunk = db.loadDbaseChunk(self.filename)
        check = ".*\<\?xml version=\"1.0\""
        result = False
        for line in file_chunk:
            if(re.match(check, line)):
                    print line
                    result = True
        return result

    def _process_based_on(self, info, filename):
        """
            The order is significant here
        """
        if(re.match(".*archive.*", info)):
            self._process_archive(filename)
        elif(re.match(".*Composite Document File V2 Document.*Excel.*", info) or
           re.match(".*Microsoft Excel 2007+.*", info) or
           not re.match(".*Composite Document File V2 Document.*Word.*", info)):
            logging.debug("Converting excel sheet to CSV")
            self._process_xls(filename)
        elif(re.match(".*Composite Document File V2 Document.*Word.*", info)):
            logging.debug("File is a word document ... Deleting.")
            self.delete()
            return False
        else:
            logging.debug("Could not determine format ... Deleting.")
            self.delete()
            return False
            
    def _process_xls(self, resource_id):
        print resource_id
        ssconvert_call = ["ssconvert", #from gnumeric package
                          "-T",
                          "Gnumeric_stf:stf_csv",
                          config.resources_path + resource_id,
                          config.resources_path + resource_id]
        print ' '.join(ssconvert_call)
        pipe = subprocess.Popen(ssconvert_call, stdout=subprocess.PIPE)
        pipe_message = pipe.stdout.read()
        print pipe_message
        self.validate()
    
    def _process_archive(self, filename):
        #unzip archive
        #check number of files
        sevenza_call = ["7za", 
                          "l",
                          config.resources_path + filename]
        pipe = subprocess.Popen(sevenza_call, stdout=subprocess.PIPE)
        pipe_message = pipe.stdout.read()
        pattern = "(\d+) files"
        number_of_files = re.search(pattern, pipe_message)
        number_of_files = int(number_of_files.group(0).split()[0])
        if(number_of_files < 2):
            #get the file name
            pattern = "\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+.{5}\s+\d+\s+\d+\s+(.*)\n"
            original_filename = re.search(pattern, pipe_message)
            original_filename = original_filename.group(0).split()[-1]
            #extract
            sevenza_call = ["7za", 
                            "e",
                            config.resources_path + filename]
            pipe = subprocess.Popen(sevenza_call, stdout=subprocess.PIPE)
            pipe_message = pipe.stdout.read()
            #move to original
            mv_call = ["mv",
                       config.resources_path + original_filename,
                       config.resources_path + filename]
            pipe = subprocess.Popen(mv_call, stdout=subprocess.PIPE)
            pipe_message = pipe.stdout.read()
        else:
            #more than 1 file in the archive
            self.delete()
            return False
    
    def _process_utf16(self, filename):
        f_in = open(filename, 'rU')
        f_out = open(filename+"-converted", 'wb')
        
        for piece in self._read_in_chunks(f_in):
            converted_piece = piece.decode('utf-16-le', errors='ignore')
            converted_piece = converted_piece.encode('ascii', errors='ignore')
            f_out.write(converted_piece)
        
        f_in.close()
        f_out.close()
        
        #move converted to original
        mv_call = ["mv",
                    filename+"-converted",
                    filename]
        pipe = subprocess.Popen(mv_call, stdout=subprocess.PIPE)
        pipe_message = pipe.stdout.read()
        
    def _read_in_chunks(self, file_object, chunk_size=1024):
        """Lazy function (generator) to read a file piece by piece.
        Default chunk size: 1k."""
        while True:
            data = file_object.read(chunk_size)
            if not data:
                break
            yield data

    def get_csv_resource_list_local(self):
        """
            Returns the list of downloaded csv CKAN resources (csv files)
        """
        csv_list = os.listdir(config.resources_path)
        return csv_list
            
if __name__ == '__main__':
    tabular_file = TabularFile('1aa9c015-3c65-4385-8d34-60ca0a875728')
    print tabular_file.get_csv_file_url()
    #print tabular_file.download()
    #print tabular_file.delete()
    #print tabular_file.get_csv_file_path()
    #print tabular_file.read_resource_file()
    #header_position = tabular_file.get_header_position()
    #print tabular_file.extract_header(header_position)
    #print tabular_file.validate()