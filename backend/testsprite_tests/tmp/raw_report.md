
# TestSprite AI Testing Report(MCP)

---

## 1️⃣ Document Metadata
- **Project Name:** backend
- **Date:** 2026-04-18
- **Prepared by:** TestSprite AI Team

---

## 2️⃣ Requirement Validation Summary

#### Test TC001 get health check status
- **Test Code:** [TC001_get_health_check_status.py](./TC001_get_health_check_status.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/75d47801-4c16-4c98-8438-2db98720cf9f
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC002 create new pipeline job
- **Test Code:** [TC002_create_new_pipeline_job.py](./TC002_create_new_pipeline_job.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 116, in <module>
  File "<string>", line 40, in test_create_new_pipeline_job
AssertionError: Create job failed with status 422: missing or invalid required form fields

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/5e8b45a6-6cbb-46e8-9d72-3c6657bf5750
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC003 get job status and metadata
- **Test Code:** [TC003_get_job_status_and_metadata.py](./TC003_get_job_status_and_metadata.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 173, in <module>
  File "<string>", line 79, in test_tc003_get_job_status_and_metadata
  File "<string>", line 34, in create_channel
  File "/var/lang/lib/python3.12/site-packages/requests/models.py", line 1024, in raise_for_status
    raise HTTPError(http_error_msg, response=self)
requests.exceptions.HTTPError: 422 Client Error: Unprocessable Entity for url: http://localhost:8000/channels

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/703ad1be-4713-4506-a302-bc47c34d7c28
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC004 list jobs for channel
- **Test Code:** [TC004_list_jobs_for_channel.py](./TC004_list_jobs_for_channel.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 86, in <module>
  File "<string>", line 18, in test_list_jobs_for_channel
AssertionError: Channel creation failed: {"detail":[{"type":"missing","loc":["body","channel_id"],"msg":"Field required","input":{"name":"Test Channel for TC004"}},{"type":"missing","loc":["body","display_name"],"msg":"Field required","input":{"name":"Test Channel for TC004"}}]}

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/b0144604-6719-40cd-8350-bdac0edd546c
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC005 upload video preview
- **Test Code:** [TC005_upload_video_preview.py](./TC005_upload_video_preview.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 60, in <module>
  File "<string>", line 33, in test_upload_video_preview
AssertionError: Expected 200 OK, got 422

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/017c6b34-f1b4-40f4-9227-86cc1e2ab9a0
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC006 delete job and associated clips
- **Test Code:** [TC006_delete_job_and_associated_clips.py](./TC006_delete_job_and_associated_clips.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 78, in <module>
  File "<string>", line 45, in test_delete_job_and_associated_clips
  File "<string>", line 14, in create_channel
  File "/var/lang/lib/python3.12/site-packages/requests/models.py", line 1024, in raise_for_status
    raise HTTPError(http_error_msg, response=self)
requests.exceptions.HTTPError: 422 Client Error: Unprocessable Entity for url: http://localhost:8000/channels

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/0a217977-49a5-4c47-a722-f83c219fbcaa
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC007 confirm speaker map and resume pipeline
- **Test Code:** [TC007_confirm_speaker_map_and_resume_pipeline.py](./TC007_confirm_speaker_map_and_resume_pipeline.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 119, in <module>
  File "<string>", line 69, in test_confirm_speaker_map_resume_pipeline
  File "<string>", line 18, in create_channel
  File "/var/lang/lib/python3.12/site-packages/requests/models.py", line 1024, in raise_for_status
    raise HTTPError(http_error_msg, response=self)
requests.exceptions.HTTPError: 422 Client Error: Unprocessable Entity for url: http://localhost:8000/channels

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/b3d6253f-0a9c-4707-9fd1-e26b0c1db4f3
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC008 list clips for channel and job
- **Test Code:** [TC008_list_clips_for_channel_and_job.py](./TC008_list_clips_for_channel_and_job.py)
- **Test Error:** Traceback (most recent call last):
  File "<string>", line 64, in test_list_clips_for_channel_and_job
AssertionError: Expected 422 status for missing channel_id, got 200

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 68, in <module>
  File "<string>", line 66, in test_list_clips_for_channel_and_job
AssertionError: Failed testing GET /clips without channel_id: Expected 422 status for missing channel_id, got 200

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/71e0ab64-1784-4352-bc12-836130e18e8b
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC009 approve clip and verify status
- **Test Code:** [TC009_approve_clip_and_verify_status.py](./TC009_approve_clip_and_verify_status.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/8b3fde77-43b1-43cf-aa5d-91502b0160ae
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC010 create new channel
- **Test Code:** [TC010_create_new_channel.py](./TC010_create_new_channel.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7c6b3d0d-b1d6-4ac8-abe0-5227636553be/fdb4f73a-a710-4d46-b525-a4a943fb14f4
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---


## 3️⃣ Coverage & Matching Metrics

- **30.00** of tests passed

| Requirement        | Total Tests | ✅ Passed | ❌ Failed  |
|--------------------|-------------|-----------|------------|
| ...                | ...         | ...       | ...        |
---


## 4️⃣ Key Gaps / Risks
{AI_GNERATED_KET_GAPS_AND_RISKS}
---