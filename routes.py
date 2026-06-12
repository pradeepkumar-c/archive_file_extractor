from flask import request, jsonify, Blueprint
from service import extractions, getjob, NotFoundError, getjobresults, DatabaseError, FileHandlingError

bp = Blueprint("snapshots", __name__)
@bp.route('/extractions/<jobid>', methods=['GET'])
def getjob_endpoint(jobid):
    try:
    
        response = getjob(jobid)
        return jsonify(response), 200
    
    except NotFoundError as e:
        print(f"Not found error in getjob_endpoint for jobid {jobid}: {e}")
        return jsonify({"error": str(e)}), 404
    
    except DatabaseError as e:
        print(f"Database error in getjob_endpoint for jobid {jobid}: {e}")
        return jsonify({"error": "Failed to retrieve job"}), 500
    
    except Exception as e:
        print(f"Unexpected error in getjob_endpoint for jobid {jobid}: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@bp.route('/extractions/<jobid>/results', methods=['GET'])
def getjobresults_endpoint(jobid):

    print(f"Received request for job results: {jobid}")

    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 10, type=int)), 100)

    try:

        response = getjobresults(jobid, page, per_page)
        return jsonify(response), 200
    
    except NotFoundError as e:
        print(f"Not found error in getjobresults_endpoint for jobid {jobid}: {e}")
        return jsonify({"error": str(e)}), 404
    
    except DatabaseError as e:
        print(f"Database error in getjobresults_endpoint for jobid {jobid}: {e}")
        return jsonify({"error": "Failed to retrieve job results"}), 500
    
    except Exception as e:
        print(f"Unexpected error in getjobresults_endpoint for jobid {jobid}: {e}")
        return jsonify({"error": "Internal server error"}), 500

@bp.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@bp.route('/extractions', methods=['POST'])
def extractions_endpoint():

    archive = request.files.get('archive')
    pattern = request.form.get('pattern')

    if not archive or not archive.filename or not pattern:
        return jsonify({'error': 'Invalid archive or pattern'}), 400
    
    try :
        
        jobid = extractions(archive, pattern)
        return jsonify({'job_id': jobid}), 202
    
    except (FileHandlingError, DatabaseError, RuntimeError) as e:
        print(f"Error processing extraction request: {e}")
        return jsonify({'error': 'Failed to process extraction request'}), 500

    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

