import json
import boto3
import traceback

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

#bedrock client
bedrock_client = boto3.client('bedrock-runtime')

#handler
def lambda_handler(event, context):

    #retrieve parameters
    question = event.get('question', '')
    system_prompt = event.get('system_prompt', '')
    tool_list = event.get('tool_list', [])
    list_to_sort = event.get('list_to_sort', [])

    #final output message
    output_message = ""
    status_code = 200

    #columns names from the opensearch index
    sort_columns = ['year', 'popularity', 'vote_average']
    
    try:
        messages = []

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
            toolConfig={
                "tools": tool_list
            },
            system=[{"text": json.dumps(system_prompt)}]
        )

        #extract message
        response_message = response['output']['message']["content"]

        logger.debug(f"sorting response_message:{response_message}")
        
        #default
        sort_by = "popularity"

        for elt in response_message:
            if "toolUse" in elt:
                sort_by = elt["toolUse"]["input"]["sort_by"]

        logger.debug(f"sort_by:{sort_by}")
        
        #sorting by descending order by default
        sorted_list = sorted(list_to_sort, key=lambda x: float(x[sort_by]), reverse=True)

        #message
        output_message = f"Here is a list of movies corresponding to your question about -{question}- sorted by -{sort_by}-."

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'sorted_by':"",
            'message': str(e),
            'search_output': []
        }
    
    return {
                'statusCode': status_code,
                'sorted_by': sort_by,
                'search_output': sorted_list,
                'message': output_message
            }