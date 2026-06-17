import os
import tarfile
import tempfile
import uuid
import zipfile
import py7zr
import glob
import time
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from model import JobStorage, FileMatch


STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
MAX_NESTING_DEPTH = 10

def extractions(archive, pattern):

    try:
        jobid = uuid.uuid4()
        archive_dir =  f"archives_{jobid}"
        os.makedirs(archive_dir, exist_ok=True)

        archive_dest = os.path.join(archive_dir, archive.filename)
        archive.save(archive_dest)

        if not pattern.startswith("**/"):
            pattern = f"**/{pattern}"

        store_job_in_db(jobid=jobid, archivefile=archive.filename, pattern=pattern, status=STATUS_PENDING)
        return str(jobid)

    except OSError as e:
        raise FileHandlingError("File operation failed") from e

    except SQLAlchemyError as e:
        raise DatabaseError("Database operation failed") from e

    except Exception as e:
        raise RuntimeError("Unexpected error during extraction") from e


def store_job_in_db(jobid, archivefile, pattern, status=STATUS_PENDING):
    print("Storing job in database for jobid:", jobid, "archivefile:", archivefile, "pattern:", pattern, "status:", status)
    try:
        extracted_file = JobStorage(jobid=jobid, 
                                archivename=archivefile,
                                pattern=pattern,
                                status=status,
                                submitted_at=datetime.utcnow())
        db.session.add(extracted_file)
        db.session.commit()
        print("Job stored in database successfully")

    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"Database error: {e}")
        raise DatabaseError("Database operation failed") from e


def getjob(jobid):
    try:
        jobid_uuid = uuid.UUID(jobid)
    except ValueError:
        raise NotFoundError("Invalid job id format")
    try:
        job = JobStorage.query.filter_by(jobid=jobid_uuid).first()
        if not job:
            raise NotFoundError('Job not found')
        num_matches = FileMatch.query.filter_by(jobid=jobid_uuid).count()
        response = {
            'jobid': str(job.jobid),
            'status': job.status,
            'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'num_matches': num_matches,
        }
        if job.error:
            response['error'] = job.error
        return response

    except SQLAlchemyError as e:
        raise DatabaseError("Database operation failed") from e


def getjobresults(jobid, page=1, per_page=10):
    try:
        jobid_uuid = uuid.UUID(jobid)
    except ValueError:
        raise NotFoundError("Invalid job id format")
    
    try:
        job = JobStorage.query.filter_by(jobid=jobid_uuid).first()
        if not job:
            raise NotFoundError('Job not found')
        pagination = FileMatch.query.filter_by(jobid=jobid_uuid).paginate(page=page, per_page=per_page, error_out=False)
        files = [file.filepath for file in pagination.items]
        print(f"getjobresults: jobid={jobid}, page={page}, per_page={per_page}, total={pagination.total}, files={files}")
        response ={
            'jobid': str(job.jobid),
            'files': files,
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
        return response

    except SQLAlchemyError as e:
        raise DatabaseError("Database operation failed") from e

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

    except SQLAlchemyError as e:
        print(f"Database error: {e}")
        db.session.rollback()
        raise DatabaseError("Database operation failed") from e

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
        
        elif tarfile.is_tarfile(archive_path):
            print("Extracting tar archive")
            with tarfile.open(archive_path, 'r') as tar_ref:
                tar_ref.extractall(extract_to)
            print("Tar archive extracted successfully")
        else:
            raise ValueError("Unsupported archive format")

    except (zipfile.BadZipFile, py7zr.exceptions.Bad7zFile, tarfile.TarError, OSError) as e:
        print(f"Error extracting archive: {e}")
        raise FileHandlingError("Archive extraction failed") from e

    except Exception as e:
        print(f"Unexpected error during archive extraction: {e}")
        raise RuntimeError("Unexpected extraction error") from e


# Recursively extract archives and find files matching pattern.
# Each archive is extracted into its own temp dir to avoid cross-contamination.
# 'processed' set (by archive basename) prevents cyclic archive structures from looping.

def extract_and_find(archive_path, pattern, level=0, nesting_chain=None, source_archive=None, processed=None):

    print(f"Extracting and finding in archive: {archive_path}, level: {level}, source_archive: {source_archive}")
    if nesting_chain is None:
        nesting_chain = []
    if source_archive is None:
        source_archive = os.path.basename(archive_path)
    if processed is None:
        processed = set()

    archive_name = os.path.basename(archive_path)

    if level > MAX_NESTING_DEPTH:
        print(f"Maximum nesting depth reached at archive: {archive_name}")
        raise RuntimeError("Maximum extraction depth reached")

    if archive_name in processed:
        print(f"Archive {archive_name} already processed, skipping.")
        return []

    processed.add(archive_name)

    extract_to = tempfile.mkdtemp()

    try:
        extract_archive(archive_path, extract_to)

        current_chain = nesting_chain + [archive_name]

        return process_extracted_files(
            extract_to,
            pattern,
            level,
            current_chain,
            source_archive,
            processed
        )

    except RuntimeError:
        print(f"Runtime error during extraction of {archive_name}")
        raise
    except Exception as e:
        print(f"Unexpected error during extraction: {e}")
        raise RuntimeError("Unexpected extraction error") from e
    finally:
        shutil.rmtree(extract_to, ignore_errors=True)


def process_extracted_files(extract_to, pattern, level, current_chain, source_archive, processed):
    print(f"Processing extracted files in: {extract_to}, level: {level}, source_archive: {source_archive}")
    matching_files = []

    found_files = find_matching_files(extract_to, pattern)

    for file in found_files:
        if zipfile.is_zipfile(file) or py7zr.is_7zfile(file) or tarfile.is_tarfile(file):
            continue

        try:
            rel_path = os.path.relpath(file, extract_to)
            logical_path = '/'.join(current_chain + [rel_path])

            matching_files.append({
                'filepath': logical_path,
                'filename': os.path.basename(file),
                'filesize': os.path.getsize(file),
                'nesting_depth': len(current_chain),
                'extracted_at': datetime.utcnow(),
                'source_archive': source_archive,
                'nesting_chain': '/'.join(current_chain)
            })
        except OSError as e:
            print(f"File metadata error for {file}: {e}")

    all_extracted = glob.glob(os.path.join(extract_to, '**', '*.*'), recursive=True)

    for nested in all_extracted:
        if not os.path.exists(nested):
            continue

        if zipfile.is_zipfile(nested) or py7zr.is_7zfile(nested) or tarfile.is_tarfile(nested):
            nested_files = extract_and_find(
                nested, pattern,
                level + 1,
                nesting_chain=current_chain,
                source_archive=source_archive,
                processed=processed
            )
            matching_files.extend(nested_files)
    print(f"Found {len(matching_files)} matching files in archive: {source_archive}")
    return matching_files


def mark_job_failed(job, error_msg):
    job.status = STATUS_FAILED
    job.error = error_msg
    job.completed_at = datetime.utcnow()

    try:
        db.session.commit()
    except SQLAlchemyError:
        print(f"Database error while updating job status for job {job.jobid}")
        db.session.rollback()

def process_job(app, jobid):
    print(f"Processing job: {jobid}")
    with app.app_context():
        try:
            job = JobStorage.query.filter_by(jobid=jobid).first()
            if not job:
                raise NotFoundError("Job not found")

            archivefile = job.archivename
            pattern = job.pattern

            archive_dir =  f"archives_{jobid}"
            archive_path = os.path.join(archive_dir, archivefile)

            matching_files = extract_and_find(archive_path, pattern)

            store_files_in_db(jobid=jobid, file_list=matching_files)

            job.status = STATUS_COMPLETED
            job.completed_at = datetime.utcnow()
            db.session.commit()
            print(f"Completed job: {jobid}")
        
        except (FileHandlingError, DatabaseError, RuntimeError ) as e:
            print(f"Error processing job {jobid}: {e}")
            mark_job_failed(job, str(e))

        except Exception as e:
            print(f"Unexpected failure for job {jobid}: {e}")
            mark_job_failed(job, str(e))

        finally:
            try:
                archive_dir = f"archives_{jobid}"
                shutil.rmtree(archive_dir, ignore_errors=True)
                print(f"Cleaned up archive directory for job {jobid}")
            except Exception as e:
                print(f"Failed to cleanup archive dir: {e}")
            db.session.remove()



def job_dispatcher(app):
    pool_size = int(os.environ.get('POOL_SIZE', 4))
    print(f"Starting job dispatcher with pool size: {pool_size}")

    executor = ThreadPoolExecutor(max_workers=pool_size)

    while True:
        jobids = []

        try:
            with app.app_context():
                pending_jobs = JobStorage.query.filter_by(
                    status=STATUS_PENDING
                ).limit(pool_size).all()
                print(f"Found {len(pending_jobs)} pending jobs: {pending_jobs}")
                for job in pending_jobs:
                    job.status = STATUS_RUNNING
                    jobids.append(job.jobid)

                print(f"Dispatching jobs: {jobids}")
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    jobids = []
                    raise

        except SQLAlchemyError as e:
            print(f"Database error in job dispatcher: {e}")

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

class FileHandlingError(Exception):
    pass