import boto3
from editor_config import R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_EDITOR_BUCKET_NAME

s3 = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
)

cors_config = {
    'CORSRules': [
        {
            'AllowedOrigins': ['https://clip.prognot.com', 'http://localhost:3000'],
            'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
            'AllowedHeaders': ['*'],
            'ExposeHeaders': ['ETag', 'Content-Length'],
            'MaxAgeSeconds': 86400
        }
    ]
}

s3.put_bucket_cors(
    Bucket=R2_EDITOR_BUCKET_NAME,
    CORSConfiguration=cors_config
)
print(f"CORS policy set on bucket: {R2_EDITOR_BUCKET_NAME}")

# Verify
response = s3.get_bucket_cors(Bucket=R2_EDITOR_BUCKET_NAME)
print("Current CORS:", response['CORSRules'])