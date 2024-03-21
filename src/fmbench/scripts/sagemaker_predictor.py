import time
import json
import logging
import sagemaker
from typing import Dict
from sagemaker.predictor import Predictor
from sagemaker.serializers import JSONSerializer
from fmbench.scripts.fmbench_predictor import FMBenchPredictor, FMBenchPredictionResponse

## set a logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SageMakerPredictor(FMBenchPredictor):
    # overriding abstract method
    def __init__(self, endpoint_name: str):
        self._predictor: Optional[sagemaker.base_predictor.Predictor] = None
        self._endpoint_name: str = endpoint_name
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
        latency = None
        try:
            st = time.perf_counter()
            response = self._predictor.predict(payload["inputs"], payload["parameters"])
            
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
                 
        except Exception as e:
            logger.error(f"get_prediction, exception occurred while getting prediction for payload={payload} "
                         f"from predictor={self._endpoint_name}, response={response}, exception={e}")
        return FMBenchPredictionResponse(response_json=response_json, latency=latency)
    
    @property
    def endpoint_name(self) -> str:
        """The endpoint name property."""
        return self._endpoint_name
    
    def calculate_cost(self, duration: float, metrics: dict) -> str:
        """Represents the function to calculate the cost of each experiment run."""
        pass
    
def create_predictor(endpoint_name: str):
    return SageMakerPredictor(endpoint_name)