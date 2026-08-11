#!/usr/bin/python3
# Version : This is Slurm Cluster hosts fix Python scripts
# Date : 2025-2-19
# Description : 1.2.1v
# Loading packages
import re
import os
import sys
import time
import base64
import hmac
import json
import yaml
import logging
import requests
import hashlib
import pandas as pd
import numpy as np
from pprint import pprint
from calendar import calendar
from datetime import datetime
import volcenginesdkcore
import volcenginesdkecs
from volcenginesdkcore.rest import ApiException
from logging.handlers import RotatingFileHandler
# loading golbar setting
yaml_dir =  'host.fix.yaml'
script_path = os.path.realpath(__file__)
script_dir = os.path.dirname(script_path)
yaml_dir = os.path.join(script_dir,yaml_dir)
# function
def logging_modles():
    # create RotatingFileHandler
    handler = RotatingFileHandler(
        filename='fix_host.log',
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    # setting log foramt
    handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    handler.setLevel(logging.INFO)
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return(logger)
# define loading_yaml function
def loading_yaml(dir,yaml_dir):
    yaml_conf_dir = os.path.join(dir, yaml_dir)
    with open(yaml_conf_dir, 'r') as file:
        yaml_content = yaml.safe_load(file)
    return yaml_content
# define describe_instance  function
def describe_instance(PATTERN,Cluster_id,api_instance):
    logging.info("Starting describe_instance function.")
    req_tag_filters = volcenginesdkecs.TagFilterForDescribeInstancesInput(
        key="ClusterID",
        values=[Cluster_id]
    )
    next_token = None
    lista = []
    try:
        while True:
            describe_instances_request = volcenginesdkecs.DescribeInstancesRequest(
                tag_filters=[req_tag_filters]
            )
            # print(describe_instances_request)
            if next_token:
                describe_instances_request.next_token = next_token
            describe_instances_request.max_results = 100
            instancelist = api_instance.describe_instances(describe_instances_request)
            # print(instancelist)
            pattern = PATTERN
            for instanceid in instancelist.instances:
                primary_ip_address = instanceid.network_interfaces[0].primary_ip_address
                ecsname = instanceid.instance_name
                match = re.search(pattern, ecsname)
                if match:
                    hostname = instanceid.hostname
                    if primary_ip_address and hostname:
                        lista.append((hostname, primary_ip_address))
                        logging.info(f"Found instance: {hostname} with IP: {primary_ip_address}")

            next_token = instancelist.next_token
            if not next_token:
                break
        logging.info("describe_instance function completed successfully.")
        
    except ApiException as e:
        logging.error(f"Exception when calling API: {e}")
    return lista
# run host fix
if __name__ == '__main__':
    # change dir
    os.chdir(script_dir)
    # loading logo Models
    logger = logging_modles()
    # loading yaml
    yaml_content = loading_yaml(script_dir,yaml_dir)
    PATTERN = yaml_content['PATTERN']
    Cluster_id = yaml_content['CLUSTER_ID']
    # 获取volcengine配置
    configuration = volcenginesdkcore.Configuration()
    configuration.ak = yaml_content['AKS']['AK']
    configuration.sk = yaml_content['AKS']['AKS']
    configuration.region = yaml_content['REGION']
    volcenginesdkcore.Configuration.set_default(configuration)
    api_instance = volcenginesdkecs.ECSApi()
    lista = describe_instance(PATTERN,Cluster_id,api_instance)
    try:
        with open('update.hosts', 'w') as file:
            file.write(yaml_content['MASTER_INFOR'])
            for item in lista:
                file.write(f"{item[1]} {item[0]}\n")
            logging.info("Successfully wrote host entries to update.hosts.")
    except Exception as e:
        logging.error(f"Failed to write to update.hosts: {e}")