#!/bin/bash

echo "Getting the path of git repository (script file path)."
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE" # if $SOURCE was a relative symlink, we need to resolve it relative to the path where the symlink file was located
done
DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"
echo $DIR

echo "Removing link: /etc/supervisor/conf.d/csv2rdf-supervisor.conf"
sudo rm /etc/supervisor/conf.d/csv2rdf-supervisor.conf

echo "Removing link: /etc/nginx/sites-enabled/csv2rdf-nginx.conf" 
sudo rm /etc/nginx/sites-enabled/csv2rdf-nginx.conf 

echo "Removing entry from /etc/hosts file..."
 
