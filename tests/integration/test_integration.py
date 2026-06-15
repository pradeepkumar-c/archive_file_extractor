
from app import db, app
import pytest
import io
import zipfile
import time

def test_create_snapshot_integration_zip(client):

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        zip_file.writestr('testfile.txt', 'This is a test file.')

    zip_buffer.seek(0)

    response = client.post('/extractions', data={
        'archive': (zip_buffer, 'test.zip'),
        'pattern': '*.txt'
    })

    assert response.status_code == 202
    jobid = response.get_json().get('job_id')
    assert jobid is not None
    print(f"Created job with ID: {jobid}")


    for _ in range(15):
        response = client.get(f'/extractions/{jobid}')
        assert response.status_code == 200
        data = response.get_json()
        if data.get('status') == 'completed':
            break
        time.sleep(1)
    else:
        pytest.fail('Job did not complete in time')

    assert data['jobid'] == jobid
    assert data['status'] == 'completed'

    response = client.get(f'/extractions/{jobid}/results')
    assert response.status_code == 200
    data = response.get_json()
    assert data['jobid'] == jobid
    assert len(data['files']) == 1
    print(f"Extracted files: {data['files']}")
    assert data['files'][0] == 'test.zip/testfile.txt'



