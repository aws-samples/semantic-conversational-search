import logging
import boto3
import json
import time
import ast

from opensearchpy import (
    OpenSearch,
    RequestsHttpConnection,
    AWSV4SignerAuth
)



#format the output list as a well formed text
@staticmethod
def format_opensearch_response_for_llm(_dict):
    result = []
    for value in enumerate(_dict["hits"]["hits"]):
        result.append("<document>\n")
        for key, value in value["_source"].items():
            result.append(f"{key}: {value}\n")
        result.append("</document>\n")
    return result



#format the output list according to what is required by the documentation.
"""
https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html#agents-lambda-response

{
    "messageVersion": "1.0",
    "response": {
        "actionGroup": "string",
        "apiPath": "string",
        "httpMethod": "string",
        "httpStatusCode": number,
        "responseBody": {
            "<contentType>": {
                "body": "JSON-formatted string" 
            }
        }
    },
    "sessionAttributes": {
        "string": "string",
    },
    "promptSessionAttributes": {
        "string": "string"
    }
}
"""
def generate_json_response(data):
    response = {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": "string",
            "apiPath": "string",
            "httpMethod": "string",
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(data)
                }
            }
        },
        "sessionAttributes": {},
        "promptSessionAttributes": {}
    }
    return response

@staticmethod
def extract_response_from_os_response(_dict):
    result = []
    for value in _dict["hits"]["hits"]:
        document = value["_source"]
        result.append(document)
    return result



#get secret from AWS secret manager
@staticmethod
def get_secret(secret_name, region_name):

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name   
        )
        return get_secret_value_response['SecretString']

    except Exception as e:
        print(e)
        return ""
    

#connect to opensearch serverless
#auth : AWSV4SignerAuth
#host: <opensearchid>.us-east-1.aoss.amazonaws.com
@staticmethod
def connect_to_aoss(auth, host):
    try:
        # create an opensearch client and use the request-signer
        aoss_client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20,
        )
        return aoss_client
    except Exception as e:
        print(e)
        return None 


@staticmethod
def standard_query_opensearch(prop_value_list, os_client, index_name, data_columns, k=10):

    # if the model is not passing a list but the element itself, we turn it into a list to comply.
    if not isinstance(prop_value_list, list):
        prop_value_list = [prop_value_list]

    #building dynamically the opensearch query
    query = {
        "query": {
            "bool": {
                "must": []
            }
        },
        "size": k,
        "sort": [
            {
                "popularity": {
                    "order": "desc"
                }
            }
        ]
    }

    for elt in prop_value_list:
        for prop, value in elt.items():
            #check that the property is valid
            if prop in data_columns:
                print(f"prop:{prop}")
                #This part deals with the fact that prop_value_list can be {"actors":"['Kate', 'Leonardo']"}
                if isinstance(value, str):
                    if "[" in value:
                        #it is a list so converting str to an actual list
                        value_list = ast.literal_eval(value)
                    else:
                        #single value
                        value_list = [value]
                        
                    #injecting the property into the filter
                    for val in value_list:
                        query["query"]["bool"]["must"].append({
                            "match": {
                                prop: {
                                    "query": val,
                                    "operator": "and"
                                }
                            }
                        })

    print(f"standard query:{query}")

    search_response = os_client.search(body=query, index=index_name)

    response = extract_response_from_os_response(search_response)

    #removing the vector_index as we are not using it in that scenario
    for elt in response:
        if "vector_index" in elt:
            elt.pop("vector_index")

    return response

#query opensearch
@staticmethod
def query_opensearch(question, os_client, index_name, data_columns, embedding_model="cohere", k=10):

    #get embeddings for the query
    question_embedding = get_embeddings_from_text(question, embedding_model, input_type="search_query")

    query = {
        "size": k,
        "query": {
            "knn": {
            "vector_index": {
                "vector": question_embedding,
                "k": k
            }
            }
        },
        "_source": data_columns
    }

    response = os_client.search(body=query, index=index_name)

    return response


#invoke claude3 model
@staticmethod
def invoke_anthropic_claude(prompt, 
                            system_prompt = "",
                            max_tokens=1024, 
                            temperature=1, 
                            top_k=250, 
                            top_p=0.999,
                            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                            anthropic_version="bedrock-2023-05-31",
                            debug=False):
    try:
        if debug:
            print("invoke_anthropic_claude function config:")
            print(json.dumps({
            'anthropic_version': anthropic_version, 
            'max_tokens': max_tokens,
            'temperature': temperature,
            'top_k': top_k, 
            'top_p': top_p,
            'messages': [{
                'role': 'user', 
                'content': [{
                'type': 'text',
                'text': prompt
                }]
            }],
            'system': system_prompt
            }))

        bedrock_client = boto3.client('bedrock-runtime')
        response = bedrock_client.invoke_model(
            modelId=modelId,
            body=json.dumps({
            'anthropic_version': anthropic_version, 
            'max_tokens': max_tokens,
            'temperature': temperature,
            'top_k': top_k, 
            'top_p': top_p,
            'messages': [{
                'role': 'user', 
                'content': [{
                'type': 'text',
                'text': prompt
                }]
            }],
            'system': system_prompt
            })
        )
        result = json.loads(response['body'].read())
        to_return = result['content'][0]['text']
        return to_return
    except Exception as e:
        print(e)

#invoke model function
@staticmethod
def invoke_embeddings_model(body, modelId):
    try:
        bedrock_client = boto3.client('bedrock-runtime')
        response = bedrock_client.invoke_model( body=body, 
                                               modelId=modelId, 
                                               accept="application/json", 
                                               contentType="application/json"
        )
        return json.loads(response['body'].read().decode('utf8'))
    except Exception as e:
        print(e)
        return None

#generic function to retrieve embeddings from either titan or cohere in Bedrock
#input_type is required for Cohere models and needs to be one of those options ["search_document","search_query","classification","clustering"]
@staticmethod
def get_embeddings_from_text(text:str, model:str, input_type="search_document"):
    try:
        if model.lower() == "titan":
            modelId = "amazon.titan-embed-text-v1"
            body = json.dumps({ "inputText": text})
            vector_json = invoke_embeddings_model(body, modelId)
            return vector_json['embedding']
        
        elif model.lower() == "cohere":
            modelId = "cohere.embed-english-v3"
            #specific configuration for cohere
            if input_type not in ["search_document","search_query","classification","clustering"]:
                #setting default value if not valid value.
                input_type = "search_query"
            
            body = json.dumps({
                "texts": [text],
                "input_type": input_type}
            )
            vector_json = invoke_embeddings_model(body, modelId)
            return vector_json['embeddings'][0]
        else:
            print("Model not recognized. Please use Titan or Cohere.")
            return None
    except Exception as e:
        print(e)
        return None

# return text in between <response></response> tags from the text
@staticmethod
def return_response_from_tag(text):
    try:
        start_index = text.index("<response>")
        end_index = text.index("</response>")
        return text[start_index+10:end_index]
    except Exception as e:
        print(e)
        return None


#simple class to create a promptTemplate
class PromptTemplate:

    #logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(message)s',
                    handlers=[logging.StreamHandler()])
    
    #template. e.g. "Answer the following question based on the context provided. If you don't know the answer, just say that you don't know.\n\nContext: {context}\n\nQuestion: {question}\nAnswer:"
    template = ""
    
    #system prompt template. e.g. "You are a helpful assistant."
    system_prompt = ""

    #prefill
    prefill = ""

    #list of input variables. e.g. ["context", "question"]
    input_variables = []

    #constructor
    def __init__(self, input_variables, template, system_prompt="", prefill=""):
        self.input_variables = input_variables
        self.template = template
        self.system_prompt = system_prompt
        self.prefill = prefill

    #function replacing strings defined in input_variables by what is in kwargs
    def format_prompt(self, **kwargs):
        try:
            prompt = self.template

            #substitute variables
            for var in self.input_variables:
                to_replace = "{" + var + "}"
                replace_by = str(kwargs[var])
                prompt = prompt.replace(to_replace, replace_by)
            
            #add prefill
            prompt = prompt + "\n" + self.prefill
            return prompt
        except Exception as e:
            self.logger.error(e)
    
    def get_prompt(self):
        return self.template
    
    def get_system_prompt(self):
        return self.system_prompt
    
    def get_prefill(self):
        return self.prefill
    
    def is_prefill_empty(self):
        return self.prefill == ""


#simple class to create a buffer memory to store the conversation
class BufferMemory:

    memory = []
    size = 0

    def __init__(self, size=5) -> None:
        self.size = size 
    
    #get memory
    def get_memory(self):
        return self.memory
    
    #reset memory
    def reset_memory(self):
        self.memory = []

    #add to memory
    def add_to_memory(self, question, answer):
        if self.size > 0:
            if len(self.memory) >= self.size:
                self.memory.pop(0) #remove the first element of the list (oldest element)

            #add the new element to the list (newest element)
            self.memory.append({"question": question, "answer": answer})

    #format memory in text form to include at the beginning of the prompt
    def format_memory_for_prompt(self):
        result = []
        for index, value in enumerate(self.memory):
            result.append(f"Question {index+1}: {value['question']}\n")
            result.append(f"Answer {index+1}: {value['answer']}\n")
        return "".join(result)

#simple class storing all information needed to handle a conversation
class ConversationalRetrievalChain:

    #logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(message)s',
                    handlers=[logging.StreamHandler()])
    
    memory = False
    os_client = None
    model = None
    index_name = None
    data_columns = []
    memory = None
    main_prompt = None
    decision_prompt = None 
    retrieval_optimisation_prompt = None

    #constructor
    def __init__(self, os_client, index_name, data_columns, main_prompt, decision_prompt, retrieval_optimisation_prompt, model="anthropic.claude-3-sonnet-20240229-v1:0", memory=None):
        self.os_client = os_client
        self.index_name = index_name
        self.model = model
        self.memory = memory
        self.data_columns = data_columns
        self.memory = memory
        self.main_prompt = main_prompt
        self.decision_prompt = decision_prompt
        self.retrieval_optimisation_prompt = retrieval_optimisation_prompt

    
    #format the output list as a well formed text
    def format_opensearch_response_for_llm(self, _dict):
        result = []
        for index, value in enumerate(_dict["hits"]["hits"]):
            result.append("<document>\n")
            for key, value in value["_source"].items():
                result.append(f"{key}: {value}\n")
            result.append("</document>\n")
        return result

    #query opensearch
    def query_opensearch(self, question, embedding_model="cohere", k=10):

        #get embeddings for the query
        question_embedding = get_embeddings_from_text(question, embedding_model, input_type="search_query")

        query = {
            "size": k,
            "query": {
                "knn": {
                "vector_index": {
                    "vector": question_embedding,
                    "k": k
                }
                }
            },
            "_source": self.data_columns
        }

        return self.os_client.search(body=query, index=self.index_name)
    
    def run(self, question, k=10, verbose=False, max_tokens=1024, temperature=0.9, top_k=250, top_p=0.999):
        

        #----------------------------------------------------------------------------------------------------------------------------
        start = time.time()
        llm_decision_question = invoke_anthropic_claude(self.decision_prompt.format_prompt(question=question, memory=self.memory.format_memory_for_prompt()), 
                            system_prompt=self.decision_prompt.get_system_prompt(),
                            max_tokens=max_tokens, 
                            temperature=0.0, 
                            top_k=250, 
                            top_p=0.999,
                            modelId=self.model,
                            debug=False)
        end = time.time()

        #managing prefill if prefill is used.s
        if not self.decision_prompt.is_prefill_empty():
            llm_decision_question = self.decision_prompt.get_prefill() + llm_decision_question

        #get response from response tags
        retrieval_required = return_response_from_tag(llm_decision_question)
        if verbose:
            self.logger.info(f"Execution time 1st LLM call: {end - start}")
            self.logger.info(f"is retrieval needed (yes/no)? -> {retrieval_required}")      

        #----------------------------------------------------------------------------------------------------------------------------

        #retrieve the document from opensearch and set the context.
        context = ""
        if retrieval_required.lower() == "yes":

            # we had the memory as context for the model to optimise the query
            start = time.time()
            llm_optim_response = invoke_anthropic_claude(self.retrieval_optimisation_prompt.format_prompt(question=question, memory=self.memory.format_memory_for_prompt()), 
                                system_prompt=self.retrieval_optimisation_prompt.get_system_prompt(),
                                max_tokens=max_tokens, 
                                temperature=0.5, 
                                top_k=250, 
                                top_p=0.999,
                                modelId=self.model,
                                debug=False)
            end = time.time()

            #managing prefill if prefill is used.s
            if not self.retrieval_optimisation_prompt.is_prefill_empty():
                llm_optim_response = self.retrieval_optimisation_prompt.get_prefill() + llm_optim_response

            llm_optim_response_cleanup = return_response_from_tag(llm_optim_response)
            if verbose:
                self.logger.info(f"Execution time 2nd LLM call: {end - start}")
                self.logger.info(f"original question:{question}")
                self.logger.info(f"optimised question:{llm_optim_response_cleanup}\n")
            
            #----------------------------------------------------------------------------------------------------------------------------
            #retrieve documents from opensearch
            os_response = self.query_opensearch(llm_optim_response, embedding_model="cohere", k=k)

            #format the response into text to include in the context.
            os_text_response = self.format_opensearch_response_for_llm(os_response)
            context = "".join(os_text_response)
            #----------------------------------------------------------------------------------------------------------------------------
        
        #set chat history
        chat_history = ""
        if self.memory is None:
            chat_history = self.memory.format_memory_for_prompt()
           
        #----------------------------------------------------------------------------------------------------------------------------
        #build the last prompt
        full_prompt = self.main_prompt.format_prompt(context=context, question=question, chat_history=chat_history)

        if verbose:
            self.logger.info("---------------------Full prompt---------------------------------")
            self.logger.info(self.main_prompt.get_system_prompt() + "\n" + full_prompt)
            self.logger.info("-----------------------------------------------------------------")

        #call llm
        start = time.time()
        llm_response = invoke_anthropic_claude(full_prompt,
                            system_prompt=self.main_prompt.get_system_prompt(),
                            max_tokens=max_tokens, 
                            temperature=temperature, 
                            top_k=top_k, 
                            top_p=top_p,
                            modelId=self.model,
                            anthropic_version="bedrock-2023-05-31", 
                            debug=False)
        end = time.time()

         #managing prefill if prefill is used.
        if not self.main_prompt.is_prefill_empty():
            llm_response = self.main_prompt.get_prefill() + llm_response

        response = return_response_from_tag(llm_response)

        if verbose:
            self.logger.info(f"RAW Response from LLM: {response}")
            self.logger.info(f"Execution time 3rd LLM call: {end - start}")
        
        #update memory
        if self.memory is None:
            self.memory.add_to_memory(question, return_response_from_tag(llm_response))
        
        return response



    