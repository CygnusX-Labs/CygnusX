#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import re
import sys
import tos
import yaml
import crcmod
import logging
import argparse
import configparser
from io import BytesIO
from datetime import datetime
import concurrent.futures
from functools import partial
from tos import DataTransferType
from dateutil.relativedelta import relativedelta
#-----------------#
config_file = "~/.SequantaTosutil.yaml"
scripts_version = '1.0v'
#-----------------#
# functions
class Crc64IO(object):
    def __init__(self, data):
        self.data = data
        self.crc64 = tos.utils.Crc64()

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def next(self):
        content = self.data.read(8 * 1024)
        if content:
            self.crc64.update(content)
            return content
        raise StopIteration

class SizeAdapter:
    def __init__(self, file_obj, size, init_offset=0):
        self.file_obj = file_obj
        self.size = size
        self.init_offset = init_offset
        self.current_offset = 0

    def read(self, size=-1):
        if self.current_offset >= self.size:
            return b''
        remaining = self.size - self.current_offset
        if size == -1 or size > remaining:
            size = remaining
        self.file_obj.seek(self.init_offset + self.current_offset)
        data = self.file_obj.read(size)
        self.current_offset += len(data)
        return data

def argparse_command():
    parser = argparse.ArgumentParser(description="SequantaTosutil Main Command")
    parser.add_argument('-v', '--version', action='version', version=scripts_version)
    parser.add_argument('-b','--debug', action='store_true', help='SequantaTosutil debug')
    subparsers = parser.add_subparsers(dest='command', help='Subcommand')
    # DataDeliver 
    DataDeliver_parser = subparsers.add_parser('DataDeliver', help='BixPipe_smk_dockerize data-deliver Command')
    DataDeliver_parser.add_argument('--OriginPATH', '-o', type=str, required=True, help='待传输数据的路径 (请输入绝对目录)')
    DataDeliver_parser.add_argument('--Bucket', '-t', type=str, required=True, help='火山云 bucket 地址 (sskyseq-product-tos/xxxxxxxxxx/xxxxxxxxxxx/)')
    DataDeliver_parser.add_argument('--projectconfig', '-p', type=str, required=True,
                                     help='标准分析 project config 文件 (project.yaml)')
    DataDeliver_parser.add_argument('--ArchiveType', '-T', type=str, required=True,
                                     choices=("ShortTerm", "LongTerm"), default="ShortTerm",
                                     help='数据保存类型 ( ShortTerm | LongTerm )')
    DataDeliver_parser.add_argument('--threads', '-j', type=int, default=10,
                                     help='启用多线程进行数据传输(默认使用10核)')
    DataDeliver_parser.add_argument('--link', '-L', action='store_true', help='上传软链接文件或文件夹指向的真实路径')     
    DataDeliver_parser.add_argument('--ak', '-A', type=str, help='火山云tos存储AK')
    DataDeliver_parser.add_argument('--sk', '-S', type=str, help='火山云tos存储SK')
    DataDeliver_parser.add_argument('--endpoint', '-e', type=str, help='bucket 挂载点', default='tos-cn-shanghai.ivolces.com')
    DataDeliver_parser.add_argument('--region', '-r', type=str, help='bucket所在区域', default='cn-shanghai')
    DataDeliver_parser.add_argument('--debug', '-b', action='store_true', help='debug')
    # Archive 
    Archive_parser = subparsers.add_parser('Archive', help='SetWorkflow Analysis Data Buckup Command')
    Archive_parser.add_argument('--OriginPATH', '-o', type=str, required=True, 
                                help='待传输数据的路径 (请输入绝对目录)')
    Archive_parser.add_argument('--Bucket', '-t', type=str, required=True, 
                                 help='火山云 bucket 地址 (sequanta-bioinfo-archive/xxxxxxx/xxxxxx/)')
    Archive_parser.add_argument('--projectconfig', '-p', type=str, required=True,
                                help='待传输数据 project.config (project.yaml)')
    Archive_parser.add_argument('--ArchiveType', '-T', type=str, required=True, 
                                choices=("ShortTerm", "LongTerm"), default="ShortTerm",
                                help='数据备份类型 ( ShortTerm | LongTerm )')
    Archive_parser.add_argument('--threads', '-j', type=int, default=10,
                                help='启用多线程进行数据传输(默认使用10核)')
    Archive_parser.add_argument('--link', '-L', action='store_true', help='上传软链接文件或文件夹指向的真实路径')     
    Archive_parser.add_argument('--ak', '-A', type=str, help='火山云tos存储AK')
    Archive_parser.add_argument('--sk', '-S', type=str, help='火山云tos存储SK')
    Archive_parser.add_argument('--endpoint', '-e', type=str, help='bucket 挂载点', default='tos-cn-shanghai.ivolces.com')
    Archive_parser.add_argument('--region', '-r', type=str, help='bucket所在区域', default='cn-shanghai')
    Archive_parser.add_argument('--debug', '-b', action='store_true', help='debug')
    # General 
    general_parser = subparsers.add_parser('General', help='general Data & tos bucket transfer Command')
    general_parser.add_argument('--OriginPATH', '-o', type=str, required=True, help='待传输数据的路径 (请输入绝对目录)')
    general_parser.add_argument('--Bucket', '-t', type=str, required=True, help='火山云 bucket 地址(xxxxxxx/xxxxxxx/xxxxxx/)')
    general_parser.add_argument('--ArchiveType', '-T', type=str, required=True, 
                                choices=("ShortTerm", "LongTerm"), default="ShortTerm",
                                help='数据备份类型 ( ShortTerm | LongTerm )')
    general_parser.add_argument('--threads', '-j', type=int, default=10,
                                help='启用多线程进行数据传输(默认使用10核)')
    general_parser.add_argument('--link', '-L', action='store_true', help='上传软链接文件或文件夹指向的真实路径') 
    general_parser.add_argument('--id', '-I', type=str, required=True, help='待传输数据项目ID')
    general_parser.add_argument('--other', '-O', type=str, required=True, help='其他额外需要添加的元数据(key1:value1,key1:value1)')
    general_parser.add_argument('--include', '-i', type=str,default='*',help='上传时对包含文件(正则表达式)的名称匹配模式')
    general_parser.add_argument('--exclude', '-E', type=str,default=None,help='上传时对不包含文件(正则表达式)的名称匹配模式')
    general_parser.add_argument('--ak', '-A', type=str, help='火山云tos存储AK')
    general_parser.add_argument('--sk', '-S', type=str, help='火山云tos存储SK')
    general_parser.add_argument('--endpoint', '-e', type=str, help='bucket 挂载点', default='tos-cn-shanghai.ivolces.com')
    general_parser.add_argument('--region', '-r', type=str, help='bucket所在区域', default='cn-shanghai')
    general_parser.add_argument('--debug', '-b', action='store_true', help='debug')
    # Delete 
    Delete_parser = subparsers.add_parser('Delete', help='delete tos bucket data Command')
    Delete_parser.add_argument('--uploadlog', '-l', type=str, required=True, help='数据上传/备份log日志')
    Delete_parser.add_argument('--project', '-p', type=str, required=True, help='删除项目ID')
    Delete_parser.add_argument('--ak', '-A', type=str, help='火山云tos存储AK')
    Delete_parser.add_argument('--sk', '-S', type=str, help='火山云tos存储SK')
    Delete_parser.add_argument('--endpoint', '-e', type=str, help='bucket 挂载点', default='tos-cn-shanghai.ivolces.com')
    Delete_parser.add_argument('--region', '-r', type=str, help='bucket所在区域', default='cn-shanghai')
    Delete_parser.add_argument('--debug', '-b', action='store_true', help='debug')
    # Config
    Config_parser = subparsers.add_parser('Config', help='SequantaTosutil Config')
    # Config_parser.add_argument('--config', '-c', type=str,default='~/.SequantaTosutil.yaml',help='SequantaTosutil Config保存位置(默认:~/.SequantaTosutil.yaml)')
    Config_parser.add_argument('--ak', '-A', type=str,required=True, help='火山云tos存储AK')
    Config_parser.add_argument('--sk', '-S', type=str,required=True, help='火山云tos存储SK')
    Config_parser.add_argument('--endpoint', '-e', type=str,required=True, help='bucket 挂载点', default='tos-cn-shanghai.ivolces.com')
    Config_parser.add_argument('--region', '-r', type=str,required=True, help='bucket所在区域', default='cn-shanghai')
    Config_parser.add_argument('--debug', '-b', action='store_true', help='debug')
    # add args
    args = parser.parse_args() 
    return args, parser

def get_argparse():
    args,parser = argparse_command()
    if args.command == None:
        parser.print_help()
        sys.exit()
    return args

def setup_logging(log_name, debug):
    logger = logging.getLogger('tos-upload-logger')
    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(log_name)
    if debug:
        file_handler.setLevel(logging.DEBUG)
    else:
        file_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    if debug:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

def create_log_name(command, args):
    user = os.environ.get('USER')
    if command in ('DataDeliver', 'Archive'):
        config = ConfigureProject(args.projectconfig)
        project_id = config['project_id']
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_name = f'{project_id}_tos_upload_{user}_{current_date}.log'
    elif command == 'general':
        project_id = args.id
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_name = f'{project_id}_tos_upload_{user}_{current_date}.log'
    elif command == 'Delete':
        project_id = args.command + '_' + args.project
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_name = f'{project_id}_tos_object_{user}_{current_date}.log'
    else:
        project_id = args.command
        current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_name = f'{project_id}_tos_{user}_{current_date}.log'
    
    return log_name

def read_tos_config(config_file):
    config_path = config_file
    if not os.path.exists(config_path):
        logger.info(f"The configuration file {config_path} does not exist")
        sys.exit(1)
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.info(f"Unable to read or parse the configuration file. {config_path}: {e}")
        sys.exit(1)

    required_keys = ['endpoint', 'region', 'ak', 'sk']
    if not all(key in config for key in required_keys):
        logger.info(f"The configuration file is missing required parameters.: {required_keys}")
        sys.exit(1)
    
    logger.info(f"SequantaTosutil will use the {config_file} configuration file")

    return {
        'endpoint': config['endpoint'],
        'region': config['region'],
        'ak': config['ak'],
        'sk': config['sk']
    }

def read_config(cfg):
    if cfg and os.path.exists(cfg):
        with open(cfg) as fi:
            config = yaml.load(fi, Loader=yaml.SafeLoader)
    return config

def read_log_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"提供的日志文件 {file_path} 不存在")
    
    with open(file_path, 'r') as file:
        log_lines = file.readlines()
    
    return log_lines

def extract_target_paths(log_lines):
    extracted_paths = []
    pattern = r'upload -> ([^ ]+) succeeded, crc64: \d+'
    for log_line in log_lines:
        match = re.search(pattern, log_line)
        if match:
            path = match.group(1)
            if not path.lower().endswith('.log'):
                extracted_paths.append(path)
    return extracted_paths
    
def build_directory_tree(paths):
    tree = {}
    for path in paths:
        parts = path.split('/')
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
        current['*'] = True
    
    return tree

def print_directory_tree(tree, indent=0):
    for key, value in tree.items():
        if key == '*':
            continue
        if '*' in value:
            continue
        else:
            print(' ' * indent + key + '/')
            if value:
                print_directory_tree(value, indent + 2)

def count_directories(tree):
    count = 0
    for key, value in tree.items():
        if value:
            count += 1 + count_directories(value)
    return count
    
def stats_tos_bucket(log_lines):
    extracted_paths = extract_target_paths(log_lines)
    directory_tree = build_directory_tree(extracted_paths)
    print("Directory Tree:")
    print_directory_tree(directory_tree)
    file_count = len(extracted_paths)
    print(f"Total number of files: {file_count}")
    return extracted_paths

def ConfigureProject(PrjCfgFile=None):
    ### read and setting config
    config = read_config(PrjCfgFile)
    return config

def logging_metadata(metadata,logger):
    for key, value in metadata.items():
        logger.info( f"Upload Data Meta.data {key} = {value}")

def CreateMetaData(configFile,delete_type,UplodType):
    config = ConfigureProject(configFile)
    if delete_type == "ShortTerm":
        current_date = datetime.now()
        new_date = current_date + relativedelta(months=3)
        delete_date = new_date.strftime("%Y-%m-%d")
        # print(" >>> \033[1;33mData deliver will Delete at :  {} \033[0m".format(delete_date))
    elif delete_type == "LongTerm":
        current_date = datetime.now()
        new_date = current_date + relativedelta(months=60)
        delete_date = new_date.strftime("%Y-%m-%d")
    # Create  metadata
    project_id = config['project_id']
    contractID = config['contractID']
    analyzer = config['analyzer']
    uploader = os.getlogin()
    metadata = {'analyzer': analyzer,
                'contractid':contractID,
                'project_id':project_id,
                'deadline': delete_date,
                'uploader':os.environ.get('USER'),
                'UplodType':UplodType}
    # print upload meta.data
    logging_metadata(metadata,logger)
    return metadata

def parse_and_merge(input_string, existing_dict):
    pattern = r'^(?:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+(?:,[a-zA-Z0-9_]+:[a-zA-Z0-9_]+)*)?$'
    if not re.match(pattern, input_string):
        raise ValueError("输入字符串格式不正确，应为 'key1:value1,key2:value2' 的形式")
    pairs = input_string.split(',')
    new_dict = {}
    for pair in pairs:
        key, value = pair.split(':', 1)
        new_dict[key] = value
    existing_dict.update(new_dict)
    return existing_dict

def GeneralMetaData(ArchiveType,command,id,other):
    if ArchiveType == "ShortTerm":
        current_date = datetime.now()
        new_date = current_date + relativedelta(months=3)
        delete_date = new_date.strftime("%Y-%m-%d")
        logger.debug(f'SequantaTosutil add delete meta.data : {delete_date}')
        # print(" >>> \033[1;33mData deliver will Delete at :  {} \033[0m".format(delete_date))
    elif ArchiveType == "LongTerm":
        current_date = datetime.now()
        new_date = current_date + relativedelta(months=60)
        delete_date = new_date.strftime("%Y-%m-%d")
        logger.debug(f'SequantaTosutil add delete meta.data : {delete_date}')
    # Create  metadata
    project_id = id
    uploader = os.environ.get('USER')
    metadata = {'project_id':project_id,
                'deadline': delete_date,
                'uploader': uploader,
                'UplodType':command}
    # add other meta.data
    metadata = parse_and_merge(other, metadata)
    logging_metadata(metadata,logger)
    logger.debug(f'SequantaTosutil add metadata : {metadata}')
    return metadata

def checkAK(AK,SK,endpoint,region,config_file):
    config_file_path = os.path.expanduser(config_file)
    if not AK and not SK: 
        config = read_tos_config(config_file_path)
        ak = config['ak']
        sk = config['sk']
        endpoint = config['endpoint']
        region = config['region']
        logger.debug(f'Get AK & SK & endpoint & region form {config_file_path}')
        logger.debug(f'SequantaTosutil ak : {ak}')
        logger.debug(f'SequantaTosutil sk : {sk}')
        logger.debug(f'SequantaTosutil endpoint : {endpoint}')
        logger.debug(f'SequantaTosutil region : {region}')
    else:
        logger.info(f"Data transfer will be performed using the tos parameter input from the command line")
        config = {'endpoint': endpoint,
                  'region': region,
                  'ak': AK,
                  'sk': SK}
    return config

def ensure_trailing_slash(bucket_path):
    if not bucket_path.endswith('/'):
        bucket_path += '/'
        logger.debug(f'Update {bucket_path}')
    return bucket_path

def get_all_files(directory):
    all_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            logger.debug(f'To be uploaded : {file}')
            file_path = os.path.join(root, file)
            all_files.append(os.path.abspath(file_path))
    return all_files

def filter_files(filelist, include_pattern="*", exclude_pattern=None):
    if include_pattern:
        include_regex = re.compile(include_pattern)
    if exclude_pattern:
        exclude_regex = re.compile(exclude_pattern)
    filtered_files = []
    for file in filelist:
        if include_pattern and not include_regex.search(file):
            logger.debug(f'upload include file : {file}')
            continue
        if exclude_pattern and exclude_regex.search(file):
            logger.debug(f'upload exclude file : {file}')
            continue
        filtered_files.append(file)
    
    return filtered_files

def UploadLog(args,log_name,logger,metadata,config,delete = False):
    # check & update Bucket format
    args.Bucket = ensure_trailing_slash(args.Bucket)
    parts = args.Bucket.split('/', 1)
    bucket_name = parts[0]
    logger.debug(f'Upload/Backup bucket name : {bucket_name}')
    object_key = parts[1] + os.path.basename(log_name)
    logger.debug(f'Upload/Backup object name : {object_key}')
    logger.debug(f'Upload/Backup file : {log_name}')
    logger.debug(f"{log_name} upload -> {bucket_name}/{object_key} ")
    content_crc64 = uploadSingleFileCRC(
            config.get('ak'), 
            config.get('sk'), 
            config.get('endpoint'), 
            config.get('region'),
            bucket_name, 
            object_key, 
            log_name)
    logger.info(f"{log_name} upload -> {bucket_name}/{object_key} succeeded, crc64: {content_crc64}")
    if delete == True :
        metadata['uplodtype'] = 'delete_log'
    else :
        metadata['uplodtype'] = 'Upload_log'
    # add meta.data info
    FixMetadata(config.get('ak'),config.get('sk'), config.get('endpoint'),config.get('region'),
                bucket_name, object_key,metadata)
    logger.debug(f"{bucket_name}/{object_key} add meta.data: {metadata}")
    
def uploadSingleFile_MD5(ak, sk, endpoint, region,bucket_name, object_key, file_name):
    import base64
    import hashlib
    hash = hashlib.md5()
    hash.update(file_name.encode())
    content_md5 = base64.b64encode(hash.digest()).decode()
    client = tos.TosClientV2(ak, sk, endpoint, region)
    try:
        resp = client.put_object(bucket_name,object_key, content=file_name, content_md5=content_md5)
        print(resp.status_code)
        # client.close()
    except Exception as e:
        print(e)
    return content_md5

def uploadSingleFileCRC(ak, sk, endpoint, region,bucket_name, object_key, file_name):
    try:
        # 创建 TosClientV2 对象，对桶和对象的操作都通过 TosClientV2 实现
        client = tos.TosClientV2(ak, sk, endpoint, region)
        # 将本地文件上传到目标桶中
        total_size = os.path.getsize(file_name)
        part_size = 1024 * 1024 * 5
        resp = client.create_multipart_upload(bucket_name, object_key)
        upload_id = resp.upload_id
        parts = []
        crc64 = tos.utils.Crc64()
        crc64_final = 0
        # file_name为本地文件的完整路径。
        # 上传分片数据
        with open(file_name, 'rb') as f:
            part_number = 1
            offset = 0
            while offset < total_size:
                num_to_upload = min(part_size, total_size - offset)
                crc64_io = Crc64IO(SizeAdapter(f, num_to_upload, init_offset=offset))
                part = client.upload_part(bucket_name, object_key, upload_id, part_number,
                                          content=crc64_io)
                if crc64_io.crc64.crc != part.hash_crc64_ecma:
                    raise Exception('crc64 not match')
                crc64_final = crc64.combine(crc64_final, crc64_io.crc64.crc, num_to_upload)
                parts.append(part)
                offset += num_to_upload
                part_number += 1
        resp = client.complete_multipart_upload(bucket_name, object_key, upload_id, parts)
        if crc64_final != resp.hash_crc64_ecma:
            raise Exception('crc64 not match')
    except tos.exceptions.TosClientError as e:
        # 操作失败，捕获客户端异常，一般情况为非法请求参数或网络异常
        print('fail with client error, message:{}, cause: {}'.format(e.message, e.cause))
    except tos.exceptions.TosServerError as e:
        # 操作失败，捕获服务端异常，可从返回信息中获取详细错误信息
        print('fail with server error, code: {}'.format(e.code))
        # request id 可定位具体问题，强烈建议日志中保存
        print('error with request id: {}'.format(e.request_id))
        print('error with message: {}'.format(e.message))
        print('error with http code: {}'.format(e.status_code))
        print('error with ec: {}'.format(e.ec))
        print('error with request url: {}'.format(e.request_url))
    except Exception as e:
        print('fail with unknown error: {}'.format(e))
    return crc64_final

def FixMetadata(ak, sk, endpoint, region,bucket_name, object_key,meta):
    try:
        client = tos.TosClientV2(ak, sk, endpoint, region,
                                 connection_time=30, socket_timeout=60,
                                 max_retry_count=3)
        client.set_object_meta(bucket_name, object_key, meta=meta)
        # client.close()
    except tos.exceptions.TosClientError as e:
        # 操作失败，捕获客户端异常，一般情况为非法请求参数或网络异常
        print('fail with client error, message:{}, cause: {}'.format(e.message, e.cause))
    except tos.exceptions.TosServerError as e:
        # 操作失败，捕获服务端异常，可从返回信息中获取详细错误信息
        print('fail with server error, code: {}'.format(e.code))
        # request id 可定位具体问题，强烈建议日志中保存
        print('error with request id: {}'.format(e.request_id))
        print('error with message: {}'.format(e.message))
        print('error with http code: {}'.format(e.status_code))
        print('error with ec: {}'.format(e.ec))
        print('error with request url: {}'.format(e.request_url))
    except Exception as e:
        print('fail with unknown error: {}'.format(e))

def process_files(OriginPATH, Bucket, meta, config, logger, 
                  operation='DataDeliver', include_pattern="*", 
                  exclude_pattern=None, max_threads=10, link=False):
    filelist = get_all_files(OriginPATH)
    # check bucket trailing
    Bucket = ensure_trailing_slash(Bucket)
    if operation == "general":
        filelist = filter_files(filelist, include_pattern, exclude_pattern)
        logger.info(f"Filter the file list using a regular expression")
    new_file_paths = [path[len(OriginPATH + '/'):] for path in filelist]
    parts = Bucket.split('/', 1)
    bucket_name = parts[0]

    def upload_file(i, bucket_name, parts, OriginPATH, config, meta, logger, link):
        object_key = parts[1] + i
        file_name = OriginPATH + '/' + i
        
        if link and os.path.islink(file_name):
            file_name = os.readlink(file_name)
            logger.debug(f"{file_name} is a symbolic link, using the actual file path: {file_name}")
        
        logger.debug(f'Upload/Backup object name : {object_key}')
        logger.debug(f'Upload/Backup file : {file_name}')
        logger.debug(f"{file_name} upload -> {bucket_name}/{object_key} ")

        content_crc64 = uploadSingleFileCRC(
            config.get('ak'), 
            config.get('sk'), 
            config.get('endpoint'), 
            config.get('region'),
            bucket_name, 
            object_key, 
            file_name)
        
        logger.info(f"{file_name} upload -> {bucket_name}/{object_key} succeeded, crc64: {content_crc64}")

        # 添加元数据信息
        FixMetadata(config.get('ak'), config.get('sk'), config.get('endpoint'), config.get('region'),
                    bucket_name, object_key, meta)
        logger.debug(f"{bucket_name}/{object_key} add meta.data: {meta}")

        return bucket_name, object_key

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        upload_func = partial(upload_file, bucket_name=bucket_name, parts=parts, OriginPATH=OriginPATH, config=config, meta=meta, logger=logger, link=link)
        results = list(executor.map(upload_func, new_file_paths))

    return results

def SequantaTosutilConfig(ak, sk, endpoint, region, logger):
    output = '~/.SequantaTosutil.yaml'
    config_file_path = os.path.expanduser(output)
    metadata = {
        'ak': ak,
        'sk': sk,
        'endpoint': endpoint,
        'region': region
    }
    logging_metadata(metadata, logger)
    with open(config_file_path, 'w') as config_file:
        yaml.dump(metadata, config_file, default_flow_style=False)
    logger.info(f"SequantaTosutil配置文件已经保存到 : {config_file_path}")

def DeleteTosObjct(ak, sk, endpoint, region, logger,bucket_name,object_key):
    try:
        logger.debug(f'Init tosClient AK {ak}')
        logger.debug(f'Init tosClient AK {sk}')
        logger.debug(f'Init tosClient AK {endpoint}')
        logger.debug(f'Init tosClient AK {region}')
        client = tos.TosClientV2(ak, sk, endpoint, region)
        client.delete_object(bucket_name, object_key)
        logger.debug(f'Delete {bucket_name}/{object_key} Object ')
    except tos.exceptions.TosClientError as e:
        print('fail with client error, message:{}, cause: {}'.format(e.message, e.cause))
    except tos.exceptions.TosServerError as e:
        print('fail with server error, code: {}'.format(e.code))
        # request id 可定位具体问题，强烈建议日志中保存
        print('error with request id: {}'.format(e.request_id))
        print('error with message: {}'.format(e.message))
        print('error with http code: {}'.format(e.status_code))
        print('error with ec: {}'.format(e.ec))
        print('error with request url: {}'.format(e.request_url))
    except Exception as e:
        print('fail with unknown error: {}'.format(e))

def DeleteObjct(ak,sk,endpoint,region,uploadlog):
    log_lines = read_log_file(uploadlog)
    delete_objects = stats_tos_bucket(log_lines)
    confirmations = 0
    while confirmations < 3:
        if confirmations == 0:
            user_input = input("项目是否到了删除日期？请输入 'yes' 确认: ")
        elif confirmations == 1:
            user_input = input("是否与PM确认过删除操作？请输入 'yes' 确认: ")
        elif confirmations == 2:
            user_input = input("项目ID与保存路径是否准确？请输入 'yes' 确认: ")
        
        if user_input.lower() == 'yes':
            confirmations += 1
        else:
            confirmations = 0
            print("确认失败，请重新输入 'yes'")
    
    for i in delete_objects:
        parts = i.split('/', 1)
        bucket_name = parts[0]
        object_key = parts[1]
        logger.info(f'Delete {bucket_name}/{object_key} Object ')
        DeleteTosObjct(ak, sk, endpoint, region, logger, bucket_name, object_key)
    return delete_objects

def sucommand(args,config_file,logger,log_name):
    if args.command == "DataDeliver":
        logger.debug(f'SequantaTosutil command : {args.command}')
        logger.debug(f'SequantaTosutil ak : {args.ak}')
        logger.debug(f'SequantaTosutil sk : {args.sk}')
        logger.debug(f'SequantaTosutil endpoint : {args.endpoint}')
        logger.debug(f'SequantaTosutil region : {args.region}')
        logger.debug(f'SequantaTosutil threads : {args.threads}')
        logger.debug(f'SequantaTosutil upload or backup project config : {args.projectconfig}')
        # loading tos config
        config = checkAK(args.ak,args.sk,args.endpoint,args.region,config_file)
        # create DataDeliver upload metadata
        metadata = CreateMetaData(args.projectconfig,
                              args.ArchiveType,
                              args.command)
        # upload file -> tos
        results = process_files(args.OriginPATH, args.Bucket, metadata, config, logger, operation='DataDeliver',max_threads= args.threads,link=args.link)
        # upload log
        log_dir = os.getcwd() + '/' + log_name
        UploadLog(args,log_dir,logger,metadata,config)

    elif args.command == "Archive":
        logger.debug(f'SequantaTosutil command : {args.command}')
        logger.debug(f'SequantaTosutil ak : {args.ak}')
        logger.debug(f'SequantaTosutil sk : {args.sk}')
        logger.debug(f'SequantaTosutil endpoint : {args.endpoint}')
        logger.debug(f'SequantaTosutil region : {args.region}')
        logger.debug(f'SequantaTosutil threads : {args.threads}')
        logger.debug(f'SequantaTosutil upload or backup project config : {args.projectconfig}')
        # loading tos config
        config = checkAK(args.ak,args.sk,args.endpoint,args.region,config_file)
        # create DataDeliver upload metadata
        metadata = CreateMetaData(args.projectconfig,
                              args.ArchiveType,
                              args.command)
        # upload file -> tos
        results = process_files(args.OriginPATH, args.Bucket,metadata, config, logger, operation='Archive',max_threads= args.threads,link=args.link)
        # upload log
        log_dir = os.getcwd() + '/' + log_name
        UploadLog(args,log_dir,logger,metadata,config)

    elif args.command == "general":
        logger.debug(f'SequantaTosutil command : {args.command}')
        logger.debug(f'SequantaTosutil ak : {args.ak}')
        logger.debug(f'SequantaTosutil sk : {args.sk}')
        logger.debug(f'SequantaTosutil endpoint : {args.endpoint}')
        logger.debug(f'SequantaTosutil region : {args.region}')
        logger.debug(f'SequantaTosutil threads : {args.threads}')
        logger.debug(f'SequantaTosutil upload or backup project config : {args.id}')
        # loading tos config
        config = checkAK(args.ak,args.sk,args.endpoint,args.region,config_file)
        # create DataDeliver upload metadata
        metadata = GeneralMetaData(args.ArchiveType,args.command,args.id,args.other)
        # upload file -> tos
        results = process_files(args.OriginPATH, args.Bucket,metadata, config,logger,
                    include_pattern=args.include, exclude_pattern=args.exclude,
                    operation='general',max_threads= args.threads,link=args.link)
        # upload log
        log_dir = os.getcwd() + '/' + log_name
        UploadLog(args,log_dir,logger,metadata,config)

    elif args.command == "Delete":
        metadata = {'project_id':args.project,
                    'Deleter': os.environ.get('USER'),
                    'UplodType':'Delete_log'}
        config = checkAK(args.ak,args.sk,args.endpoint,args.region,config_file)
        delete_objects = DeleteObjct(config['ak'],config['sk'],config['endpoint'],config['region'],args.uploadlog)
        log_dir = os.getcwd() + '/' + log_name
        # upload delete log to tos
        args.Bucket = common_directory = os.path.commonpath(delete_objects) + "/"
        UploadLog(args,log_dir,logger,metadata,config,delete = True)

    elif args.command == "Config":
        SequantaTosutilConfig(args.ak, args.sk, args.endpoint, args.region,logger)

if __name__ == '__main__':
    args = get_argparse()
    # init loggewr
    log_name = create_log_name(args.command,args)
    logger = setup_logging(log_name, debug=args.debug)
    # run sucommand
    sucommand(args,config_file,logger,log_name)