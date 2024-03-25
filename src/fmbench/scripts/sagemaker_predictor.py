import time
import json
import logging
import sagemaker
from typing import Dict
from fmbench.utils import count_tokens
from sagemaker.predictor import Predictor
from sagemaker.serializers import JSONSerializer
from fmbench.scripts.fmbench_predictor import FMBenchPredictor, FMBenchPredictionResponse

## set a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SageMakerPredictor(FMBenchPredictor):
    # overriding abstract method
    def __init__(self, endpoint_name: str, inference_spec: Dict | None):
        self._predictor: Optional[sagemaker.base_predictor.Predictor] = None
        self._endpoint_name: str = endpoint_name
        self._inference_spec = inference_spec
        try:
            # Create a SageMaker Predictor object
            self._predictor = Predictor(
                endpoint_name=self._endpoint_name,
                sagemaker_session=sagemaker.Session(),
                serializer=JSONSerializer()
            )
        except Exception as e:
            logger.error(f"create_predictor, exception occured while creating predictor for endpoint_name={self._endpoint_name}, exception={e}")
        logger.info(f"__init__ self._predictor={self._predictor}")
        
    def get_prediction(self, payload: Dict) -> FMBenchPredictionResponse:
        response_json = None
        response = None
        latency = None
        prompt_tokens = None
        completion_tokens = None

        ## represents the number of tokens in the prompt payload -- TO ABSTRACT THIS IN THE FUTURE ITERATION
        prompt_tokens = count_tokens(payload["inputs"])

        try:
            st = time.perf_counter()
            split_input_and_inference_params = None
            if self._inference_spec is not None:
                split_input_and_inference_params = self._inference_spec.get("split_input_and_parameters")
            if split_input_and_inference_params is True:
                response = self._predictor.predict(payload["inputs"], payload["parameters"])                
            else:
                response = self._predictor.predict(payload)
            
            latency = time.perf_counter() - st
            if isinstance(response, bytes):
                response = response.decode('utf-8')
            response_json = json.loads(response)
            
            if isinstance(response_json, list):
                response_json = response_json[0]
            # add a key called completion, if not there
            if response_json.get("generated_text") is None:            
                if response_json.get("predicted_label") is not None:                    
                    response_json["generated_text"] = response_json.get("predicted_label")
            
            ## counts the completion tokens for the model using the default/user provided tokenizer - to change this too in the future iteration and abstract it out
            completion_tokens = count_tokens(response_json.get("generated_text"))

        except Exception as e:
            logger.error(f"get_prediction, exception occurred while getting prediction for payload={payload} "
                         f"from predictor={self._endpoint_name}, response={response}, exception={e}")
        return FMBenchPredictionResponse(response_json=response_json, latency=latency, completion_tokens=completion_tokens, prompt_tokens=prompt_tokens)
    
    @property
    def endpoint_name(self) -> str:
        """The endpoint name property."""
        return self._endpoint_name
    
    def calculate_cost(self, instance_type: str, config: dict, duration: float, metrics: dict) -> str:
        """Represents the function to calculate the cost of each experiment run."""
        experiment_cost = 0.0
        metrics = None ## this is not needed for now, will be used in the case of bedrock
        # sagemaker experiment pricing calculation
        # price of the given instance for this experiment 
        hourly_rate = config['pricing'].get(instance_type, {})
        logger.info(f"the hourly rate for {config['general']['model_name']} running on {instance_type} is {hourly_rate}")

        cost_per_second = hourly_rate / 3600
        logger.info(f"the rate for {config['general']['model_name']} running on {instance_type} is {cost_per_second} per second")
        
        experiment_cost = cost_per_second * duration
        return experiment_cost
    
def create_predictor(endpoint_name: str, inference_spec: Dict | None):
    return SageMakerPredictor(endpoint_name, inference_spec)