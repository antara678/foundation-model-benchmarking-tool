# Import necessary libraries
import os
import json
import time
import boto3
import logging
import sagemaker
from typing import Dict
from pathlib import Path
from sagemaker.huggingface import HuggingFaceModel
from sagemaker.huggingface import get_huggingface_llm_image_uri

# globals
HF_TOKEN_FNAME: str = os.path.join(os.path.dirname(os.path.realpath(__file__)), "hf_token.txt")

## set a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

## set your model_name here
model_name: str = "meta-llama/Llama-2-70b-chat-hf"

## Initialize your S3 client for your model uploading
s3_client = boto3.client('s3')

## ------------- Use your specific execution role --------------------------------------------

# role=sagemaker.get_execution_role()  # execution role for the endpoint
sess=sagemaker.session.Session()  # sagemaker session for interacting with different AWS APIs
bucket=sess.default_bucket()  # bucket to house artifacts
model_bucket=sess.default_bucket()  # bucket to house artifacts

## ------------- Define the location of your s3 prefix for model artifacts ----------------------------------------

region=sess._region_name
print(f"region name -> {region}")

## Define your account/session id
account_id=sess.account_id()

## ------------- Initialize the sagemaker and sagemaker runtime clients -------------------------------------------

sm_client = boto3.client("sagemaker")
smr_client = boto3.client("sagemaker-runtime")

## ---------------------------------------------------------------------------------------------------------

## Function to get the hugging face image uri
def get_huggingface_image_uri():
    # retrieve the llm image uri
    llm_image = get_huggingface_llm_image_uri(
    "huggingface",
    version="0.9.3"
    )

    print(f"The image uri being used -> {llm_image}")
    return llm_image

## Function to create the llm hugging face model
def create_hugging_face_model(experiment_config, role_arn):

    # Define Model and Endpoint configuration parameter
    model_config = {
    'HF_MODEL_ID': model_name,
    'SM_NUM_GPUS': json.dumps(experiment_config['env']['NUMBER_OF_GPU']), # Number of GPU used per replica
    'MAX_INPUT_LENGTH': json.dumps(4090),  # Max length of input text
    'MAX_TOTAL_TOKENS': json.dumps(4096),  # Max length of the generation (including input text)
    'MAX_BATCH_TOTAL_TOKENS': json.dumps(8192),  # Limits the number of tokens that can be processed in parallel during the generation
    'HUGGING_FACE_HUB_TOKEN': Path(HF_TOKEN_FNAME).read_text().strip()
    }

    # create HuggingFaceModel with the image uri
    llm_model = HuggingFaceModel(
    role=role_arn,
    image_uri=experiment_config['image_uri'],
    env=model_config
    )

    print(f"Hugging face model defined using {model_config} -> {llm_model}")
    return llm_model

## Function to check the status of the endpoint
def check_endpoint_status(endpoint_name):
    resp = sm_client.describe_endpoint(EndpointName=endpoint_name)
    status = resp["EndpointStatus"]
    while status == "Creating":
        time.sleep(60)
        resp = sm_client.describe_endpoint(EndpointName=endpoint_name)
        status = resp["EndpointStatus"]
    return status

## Deploy the hugging face model
def deploy_hugging_face_model(experiment_config: Dict, llm_model):
    ## Now that the inference uri has been retrieved and we have the configurations for the llm, deploying the model
    llm = llm_model.deploy(
        initial_instance_count=experiment_config['env']['INSTANCE_COUNT'],
        instance_type=experiment_config['instance_type'],
        container_startup_health_check_timeout=experiment_config['env']['HEALTH_CHECK_TIMEOUT'], # 10 minutes to be able to load the model
        )
    
    ## Endpoint name
    endpoint_name = llm.endpoint_name

    return endpoint_name

# Function to deploy the model and create the endpoint
def deploy(experiment_config: Dict, role_arn: str) -> Dict:
    logger.info("deploying the model using the llm_model and the configurations ....")

    print(f"first, retrieving the hugging face image uri .....")
    llm_image = get_huggingface_image_uri()
    logger.info(f"retrieved the inference uri -> {llm_image}")

    print(f"Setting the model configurations .....")
    llm_model = create_hugging_face_model(experiment_config, role_arn)
    logger.info(f"the llm_model has been defined .... {llm_model}")

    llm_endpoint = deploy_hugging_face_model(experiment_config, llm_model)
    logger.info("Deploying the model now ....")

    status = check_endpoint_status(llm_endpoint)
    logger.info(f"Endpoint status: {status}")

    return dict(endpoint_name=llm_endpoint, experiment_name=experiment_config['name'])
