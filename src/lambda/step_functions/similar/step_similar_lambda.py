import json
import boto3
from utils import llm_utils
import time
import os
import re
import traceback

from opensearchpy import (
    AWSV4SignerAuth
)

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#bedrock client
bedrock_client = boto3.client('bedrock-runtime')

#extract answer from tags
def extract_answer(text, tag="answer"):
    pattern = f'<{tag}>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    else:
        return None

#converse API call
def converse_api_call_no_tool(question, history_list, system_prompt, bedrock_client):
    
    messages = []

    if history_list:
        messages = history_list
    
    user_message = {
        "role": "user",
        "content": [
            { "text": json.dumps(question) } 
        ],
    }
    messages.append(user_message)

    response = bedrock_client.converse(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        messages=messages,
        inferenceConfig={
            "maxTokens": 2000,
            "temperature": 0,
            "topP": 1
        },
        system=[{"text": json.dumps(system_prompt)}]
    )

    #extract message
    response_message = response['output']['message']["content"]

    return response_message[0]["text"]



#handler
def lambda_handler(event, context):

    #retrieve parameters
    question = event.get('question', '')
    system_prompt_similar_from_question = event.get('system_prompt_similar_from_question', '')
    system_prompt_similar_from_history = event.get('system_prompt_similar_from_history', '')
    history_list = event.get('history', [])
    index_name = event.get('index_name', '')
    os_host = event.get('os_host', '')
    number_results = event.get('number_results', 10)
    
    data_columns = ['tmdb_id', 'original_language', 'original_title', 'description', 'genres', 'year', 'keywords', 'director', 'actors', 'popularity', 'popularity_bins',
                  'vote_average', 'vote_average_bins']
    
    #final output
    similar_list = []
    movie_name = ""
    status_code = 200
    output_message = ""

    try:

        #------ Check history list first ---------

        #history list is empty so we need to extract the movie name from the question
        if not history_list:
            
            #extract movie name from question
            response = converse_api_call_no_tool(question, [], system_prompt_similar_from_question, bedrock_client)
            movie_name = extract_answer(response)

        # if history list is not empty, we need to take into consideration for the question
        else:
            #extract movie name from question
            response = converse_api_call_no_tool(question, history_list, system_prompt_similar_from_history, bedrock_client)
            movie_name = extract_answer(response)

        #debug
        logger.debug(f"history_list:{history_list}")
        logger.debug(f"movie_name:{movie_name}")
        logger.debug(f"movie name extract response:{response}")

        if movie_name:
            #building the filter for opensearch
            prop_value_list = [{"original_title": movie_name}]

            #retrieve the information about the movie using standard search

            #get region
            region_name = os.environ.get('AWS_REGION')
            #auth object required to connect to opensearch
            credentials = boto3.Session().get_credentials()
            auth = AWSV4SignerAuth(credentials, region_name, 'aoss')

            #connecting to opensearch serverless
            os_client = llm_utils.connect_to_aoss(auth, os_host)

            #querying opensearch
            start_time = time.time()
            response_aoss = llm_utils.standard_query_opensearch(prop_value_list, os_client, index_name, data_columns, k=1)
            end_time = time.time()
            execution_time = end_time - start_time

            logger.debug(f"Querying OpenSearch took {execution_time:.6f} seconds.")

            response_aoss_str = json.dumps(response_aoss)

            logger.debug(f"response_aoss:{response_aoss}")

            #extracting the tmdb_id from the response
            tmdb_id = ""
            if response_aoss and response_aoss[0]:
                tmdb_id = response_aoss[0]["tmdb_id"]

            #now we do a semantic search to retrieve the results
            #querying opensearch
            start_time = time.time()
            os_response = llm_utils.query_opensearch(response_aoss_str, os_client, index_name, data_columns, embedding_model="cohere", k=number_results+1)
            end_time = time.time()
            execution_time = end_time - start_time

            logger.debug(f"Querying OpenSearch took {execution_time:.6f} seconds.")

            #extract object from os response
            similar_list = llm_utils.extract_response_from_os_response(os_response)

            #making sure that the list doesn't include the movie we used to for similar movies (very likely)
            if tmdb_id != "":
                similar_list = [item for item in similar_list if item["tmdb_id"] != tmdb_id]

            output_message = f"Here is a list of movies similar to {movie_name}"
            
        else:
            logger.error("No movie name found in the question or history list.")
            status_code = 500
            output_message = "No movie name found in the question or history list."


    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'message': str(e),
            'search_output': [],
            'question': question,
            'movie_name':movie_name
        }   

    return {
            'statusCode': status_code,
            'search_output': similar_list,
            'question': question,
            'movie_name':movie_name,
            'message' : output_message
        }