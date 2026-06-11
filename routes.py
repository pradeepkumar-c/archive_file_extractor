from flask import app, request, jsonify, json, Blueprint
from werkzeug.exceptions import BadRequest
from service import extractions, getjob, NotFoundError, getjobresults
from model import db


bp = Blueprint("snapshots", __name__)
@bp.route('/extractions/<jobid>', methods=['GET'])
def getjob_endpoint(jobid):
    try:
        response =getjob(jobid)
    
        return jsonify(response), 200
    except NotFoundError as e:
        return jsonify({"error": str(e)}), 404

@bp.route('/extractions/<jobid>/results', methods=['GET'])
def getjobresults_endpoint(jobid):
    print(f"Received request for job results: {jobid}")
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    try:
        response = getjobresults(jobid, page, per_page)
        return jsonify(response), 200
    except NotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500

@bp.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@bp.route('/extractions', methods=['POST'])
def extractions_endpoint():
    if 'archive' not in request.files or 'pattern' not in request.form:
        return jsonify({'error': 'Missing archive or pattern'}), 400

    try :
        archive = request.files['archive']
        pattern = request.form['pattern']
        response = extractions(archive, pattern)
        return jsonify(response), 202 if 'error' not in response else 500
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
