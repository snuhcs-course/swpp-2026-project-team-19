# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #16). Reviewed by Haeul Yang.
"""In-memory stand-in for the boto3 S3 client calls that S3ImageStorage makes."""

import io

from botocore.exceptions import ClientError


class FakeS3Client:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)][0])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://{Params['Bucket']}.s3.example.com/{Params['Key']}?expires={ExpiresIn}"
