import os
import tempfile
import uuid
import zipfile
import py7zr
import glob
import time
import shutil
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from extensions import db
from model import JobStorage, FileMatch


STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'

def extractions(archive, pattern):
    try:
        temp_dir = tempfile.mkdtemp()

        archive_path = os.path.join(temp_dir, archive.filename)
        archive.save(archive_path)

        jobid = uuid.uuid4()
        acrhive_dir =  f"archives_{jobid}"
        os.makedirs(acrhive_dir, exist_ok=True)

        archive_dest = os.path.join(acrhive_dir, archive.filename)
        shutil.copy2(archive_path, archive_dest)

        res = store_job_in_db(jobid=jobid, archivefile=archive.filename, pattern=pattern, status=STATUS_PENDING)
        if res == True:
            return {'job_id': jobid}
        else:
            return {'job_id': jobid, 'error': 'Extraction failed'}
        
    except Exception as e:
        print(f"Error in extractions endpoint: {e}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

def getjob(jobid):
    job = JobStorage.query.filter_by(jobid=jobid).first()
    if not job:
        raise NotFoundError('Job not found')
    num_matches = FileMatch.query.filter_by(jobid=jobid).count()
    response = {
        'jobid': jobid,
        'status': job.status,
        'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'num_matches': num_matches,
    }
    if job.error:
        response['error'] = job.error
    return response

def getjobresults(jobid, page=1, per_page=10):
    try:
        job = JobStorage.query.filter_by(jobid=jobid).first()
        if not job:
            raise NotFoundError('Job not found')
        pagination = FileMatch.query.filter_by(jobid=jobid).paginate(page=page, per_page=per_page, error_out=False)
        files = [file.filepath for file in pagination.items]
        print(f"getjobresults: jobid={jobid}, page={page}, per_page={per_page}, total={pagination.total}, files={files}")
        response ={
            'jobid': jobid,
            'files': files,
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
        return response
    except NotFoundError as e:
        return {'error': str(e)}
    except Exception as e:
        print(f"Error in getjobresults_endpoint: {e}")
        return {'error': 'Internal server error'}

def store_job_in_db(jobid, archivefile, pattern, status=STATUS_PENDING):
    print("Storing job in database for jobid:", jobid, "archivefile:", archivefile, "pattern:", pattern, "status:", status)
    try:
        extracted_file = JobStorage(jobid=jobid, archivename=archivefile, pattern=pattern, status=status, submitted_at=datetime.utcnow())
        db.session.add(extracted_file)
        db.session.commit()
        print("Job stored in database successfully")
        return True
    except Exception as e:
        print(f"Error storing job in database: {e}")
        db.session.rollback()
        return False

def store_files_in_db(jobid, file_list):
    print("Storing files in database for jobid:", jobid, file_list)
    try:
        for file_info in file_list:
            file_match = FileMatch(
                jobid=jobid,
                filepath=file_info['filepath'],
                filename=file_info['filename'],
                filesize=file_info['filesize'],
                nesting_depth=file_info['nesting_depth'],
                extracted_at=file_info['extracted_at'],
                source_archive=file_info['source_archive'],
                nesting_chain=file_info['nesting_chain']
            )
            db.session.add(file_match)
        db.session.commit()
        print("Files stored in database successfully")
        return True
    except Exception as e:
        print(f"Error storing files in database: {e}")
        db.session.rollback()
        raise RuntimeError(f"DB insert failed: {str(e)}")

def find_matching_files(search_dir, pattern):
    search_path = os.path.join(search_dir, pattern)
    print(f"Searching for files with pattern: {search_path}")
    return glob.glob(search_path, recursive=True)

def extract_archive(archive_path, extract_to):
    print(f"Extracting archive: {archive_path} to {extract_to}")
    try:
        if zipfile.is_zipfile(archive_path):
            print("Extracting zip archive")
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            print("Zip archive extracted successfully")
        elif py7zr.is_7zfile(archive_path):
            print("Extracting 7z archive")
            with py7zr.SevenZipFile(archive_path, mode='r') as z:
                z.extractall(path=extract_to)
            print("7z archive extracted successfully")
        else:
            raise ValueError("Unsupported archive format")

    except Exception as e:
        print(f"Error extracting archive: {e}")
        raise RuntimeError(f"Error extracting archive: {str(e)}")
    return True

MAX_NESTING_DEPTH = 10

# Recursively extract archives and find files matching pattern.
# Each archive is extracted into its own temp dir to avoid cross-contamination.
# 'processed' set (by archive basename) prevents cyclic archive structures from looping.
def extract_and_find(archive_path, pattern, level=0, nesting_chain=None, source_archive=None, processed=None):
    if nesting_chain is None:
        nesting_chain = []
    if source_archive is None:
        source_archive = os.path.basename(archive_path)
    if processed is None:
        processed = set()

    archive_name = os.path.basename(archive_path)

    if level > MAX_NESTING_DEPTH:
        print(f"Maximum extraction depth ({MAX_NESTING_DEPTH}) reached at: {archive_path}")
        raise RuntimeError("Maximum extraction depth reached")

    if archive_name in processed:
        print(f"Skipping already-processed archive to avoid loop: {archive_name}")
        return [], None
    processed.add(archive_name)

    extract_to = tempfile.mkdtemp()
    try:
        result = extract_archive(archive_path, extract_to)
        if not result:
            raise RuntimeError("Error extracting archive")

        matching_files = []
        current_chain = nesting_chain + [archive_name]

        # Find all files in extracted dir that match the pattern (non-archive files)
        found_files = find_matching_files(extract_to, pattern)
        for file in found_files:
            # Skip if this file is itself an archive (will be handled by recursion)
            if zipfile.is_zipfile(file) or py7zr.is_7zfile(file):
                continue
            try:
                rel_path = os.path.relpath(file, extract_to)
                logical_path = '/'.join(current_chain + [rel_path])
                file_info = {
                    'filepath': logical_path,
                    'filename': os.path.basename(file),
                    'filesize': os.path.getsize(file),
                    'nesting_depth': len(current_chain),
                    'extracted_at': datetime.utcnow(),
                    'source_archive': source_archive,
                    'nesting_chain': '/'.join(current_chain)
                }
                matching_files.append(file_info)
            except Exception as e:
                print(f"Error getting file info for {file}: {e}")

        # Find nested archives in the extracted dir
        all_extracted = glob.glob(os.path.join(extract_to, '**', '*.*'), recursive=True)
        for nested in all_extracted:
            if not os.path.exists(nested):
                continue
            if zipfile.is_zipfile(nested) or py7zr.is_7zfile(nested):
                nested_files = extract_and_find(
                    nested, pattern, level + 1,
                    nesting_chain=current_chain,
                    source_archive=source_archive,
                    processed=processed
                )
                matching_files.extend(nested_files)

        return matching_files
    finally:
        shutil.rmtree(extract_to, ignore_errors=True)


def process_job(app, jobid):
    with app.app_context():
        try:
            job = JobStorage.query.filter_by(jobid=jobid).first()
            if not job:
                return

            job.status = STATUS_RUNNING
            db.session.commit()

            archivefile = job.archivename
            pattern = job.pattern
            archive_dir =  f"archives_{jobid}"
            archive_path = os.path.join(archive_dir, archivefile)

            matching_files = extract_and_find(archive_path, pattern)

            store_files_in_db(jobid=jobid, file_list=matching_files)

            job.status = STATUS_COMPLETED
            job.completed_at = datetime.utcnow()
            db.session.commit()

        except Exception as e:
            print(f"Extraction failed for job {jobid}: {e}")

            job.status = STATUS_FAILED
            job.error = str(e)
            job.completed_at = datetime.utcnow()

            db.session.commit()

        finally:
            db.session.remove()


def job_dispatcher(app):
    pool_size = int(os.environ.get('POOL_SIZE', 4))
    print(f"Starting job dispatcher with pool size: {pool_size}")

    executor = ThreadPoolExecutor(max_workers=pool_size)

    while True:
        jobids = []

        with app.app_context():
            pending_jobs = JobStorage.query.filter_by(status=STATUS_PENDING).limit(pool_size).all()

            for job in pending_jobs:
                job.status = STATUS_RUNNING
                jobids.append(job.jobid)

            db.session.commit()

        for jid in jobids:
            executor.submit(process_job, app, jid)

        time.sleep(2)

class ValidationError(Exception):
    def __init__(self, error_body):
        self.error_body = error_body

class NotFoundError(Exception):
    pass

class DatabaseError(Exception):
    pass