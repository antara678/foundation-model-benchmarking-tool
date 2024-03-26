import os
import boto3
import logging
from litellm import embedding ## import litellm for bedrock model support: embedding models in this case
from litellm import completion ## support for text generation models on bedrock
from typing import Dict, Optional
from fmbench.scripts.fmbench_predictor import FMBenchPredictor, FMBenchPredictionResponse

## set a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

## represents the current bedrock embedding models
EMBEDDING_MODELS: list[str] = ["amazon.titan-embed-text-v1", "cohere.embed-english-v3", "cohere.embed-multilingual-v3"] 

## Represents the class to predict using a bedrock rest API 
class BedrockPredictor(FMBenchPredictor):
    ## initialize the service name
    service_name: str = "bedrock"
    # overriding abstract method
    def __init__(self, endpoint_name: str, inference_spec: Dict | None):
        try: ## initializing some of the variables in the contructor 
            self._endpoint_name = endpoint_name
            self._inference_spec = inference_spec
            self._predictor = boto3.client('bedrock-runtime')
            self.aws_region = boto3.Session().region_name
            self.bedrock_model = f"{self.service_name}/{self.endpoint_name}"
            self.response_json = {}
            logger.info(f"__init__ self._predictor={self._predictor}")
        except Exception as e:
            logger.error(f"Exception occurred while creating predictor/initializing variables for endpoint_name={self._endpoint_name}, exception={e}")
            self._predictor = None

    def get_prediction(self, payload: Dict) -> FMBenchPredictionResponse:
        ## Represents the prompt payload
        prompt_input_data = payload['inputs']
        os.environ["AWS_REGION_NAME"] = self.aws_region
        try:
            ## Represents calling the litellm completion/messaging api utilizing the completion/embeddings API
            ## [CLAUDE, LLAMA, ai21, MISTRAL, MIXTRAL, COHERE]
            logger.info(f"Invoking {self.bedrock_model} to get inference....")
            response = completion(
            model=self.bedrock_model,
            messages=[{ "content": prompt_input_data,"role": "user"}], 
            )

            ## iterate through the entire model response
            for choice in response.choices:
                ## extract the message and the message's content from litellm
                if choice.message and choice.message.content:
                    ## extract the response from the dict
                    self.response_json["generated_text"] = choice.message.content
                    break

            # Extract number of input and completion prompt tokens (this is the same structure for embeddings and text generation models on Amazon Bedrock)
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            # Extract latency in seconds
            latency_ms = response._response_ms
            latency = latency_ms / 1000
        except Exception as e:
            logger.error(f"Exception occurred during prediction for endpoint_name={self._endpoint_name}, exception={e}")
        return FMBenchPredictionResponse(response_json=self.response_json, latency=latency, completion_tokens=completion_tokens, prompt_tokens=prompt_tokens)

    def calculate_cost(self, instance_type, config: dict, duration: float, metrics: dict) -> float:
        """Represents the function to calculate the cost for Bedrock experiments."""
        experiment_cost: Optional[float] = 0.0
        try:
            if metrics:
                prompt_tokens = metrics.get("all_prompts_token_count", )
                completion_tokens = metrics.get("all_completions_token_count", )
                # Retrieve the pricing information for the instance type
                instance_pricing = config['pricing'].get(instance_type, [])
                logger.info(f"pricing dict: {instance_pricing}")
                # Calculate cost based on the number of input and output tokens
                input_token_cost = 0.0
                output_token_cost = 0.0
                for pricing in instance_pricing:
                    input_token_cost += (prompt_tokens / 1000.0) * pricing.get('input-per-1k-tokens', 0)
                    output_token_cost += (completion_tokens / 1000.0) * pricing.get('output-per-1k-tokens', 0)
                logger.info(f"input per 1k token pricing: {input_token_cost}")
                logger.info(f"output per 1k token pricing: {output_token_cost}")
                experiment_cost = input_token_cost + output_token_cost
        except Exception as e:
            logger.error(f"Exception occurred during experiment cost calculation....., exception={e}")
        return experiment_cost

    @property
    def endpoint_name(self) -> str:
        """The endpoint name property."""
        return self._endpoint_name
    
## subclass of BedrockPredictor for embedding models supported on Amazon Bedrock
class BedrockPredictorEmbeddings(BedrockPredictor):
    def get_prediction(self, payload: Dict) -> FMBenchPredictionResponse:
        ## Represents the prompt payload
        prompt_input_data = payload['inputs']
        ## getting the aws account region as an environment variable as declared in the litellm documentation
        os.environ["AWS_REGION_NAME"] = self.aws_region
        try:
            logger.info(f"Invoking {self.bedrock_model} to get inference....")
            response = embedding(
                model=self.bedrock_model,
                input=[prompt_input_data],
            )

            embedding_vector = response.data[0]["embedding"]
            self.response_json["generated_text"] = str(embedding_vector)
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.total_tokens

            latency_ms = response._response_ms
            latency = latency_ms / 1000
        except Exception as e:
            logger.error(f"Exception occurred during prediction for endpoint_name={self._endpoint_name}, exception={e}")
        return FMBenchPredictionResponse(response_json=self.response_json, latency=latency, completion_tokens=completion_tokens, prompt_tokens=prompt_tokens)


def create_predictor(endpoint_name: str, inference_spec: Dict | None):
    if endpoint_name in EMBEDDING_MODELS: ## handling for embedding models
        return BedrockPredictorEmbeddings(endpoint_name, inference_spec) ## create a github issue
    else: ## handling for all text generation models
        return BedrockPredictor(endpoint_name, inference_spec)