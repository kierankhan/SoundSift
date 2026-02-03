#pragma once
#include <JuceHeader.h>

class ApiClient
{
public:
    ApiClient(const juce::String& baseUrl = "http://localhost:8000")
        : baseUrl(baseUrl) {}
    
    void indexFolder(const juce::String& folderPath,
                     std::function<void(bool, juce::var)> callback)
    {
        juce::DynamicObject::Ptr json = new juce::DynamicObject();
        json->setProperty("file_path", folderPath);
        sendPostRequest("/index/folder", json, callback);
    }
    
    void queryText(const juce::String& queryText, int topK,
                   std::function<void(bool, juce::var)> callback)
    {
        juce::DynamicObject::Ptr json = new juce::DynamicObject();
        json->setProperty("text", queryText);
        json->setProperty("top_k", topK);
        sendPostRequest("/query/text", json, callback);
    }
    
    void loadIndex(std::function<void(bool, juce::var)> callback)
    {
        auto json = new juce::DynamicObject();
        sendPostRequest("/load", json, callback);
    }
    
private:
    juce::String baseUrl;
    
    void sendPostRequest(const juce::String& endpoint,
                        juce::DynamicObject::Ptr jsonData,
                        std::function<void(bool, juce::var)> callback)
    {
        juce::String jsonString = juce::JSON::toString(juce::var(jsonData.get()));
        juce::String fullUrl = baseUrl + endpoint;
        
        juce::Thread::launch([fullUrl, jsonString, callback]()
        {
            juce::URL url(fullUrl);
            url = url.withPOSTData(jsonString);
            
            int statusCode = 0;
            
            auto stream = url.createInputStream(
                juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
                    .withExtraHeaders("Content-Type: application/json")
                    .withConnectionTimeoutMs(30000)
                    .withStatusCode(&statusCode)
            );
            
            bool success = (stream != nullptr && statusCode == 200);
            juce::String responseText;
            
            if (stream != nullptr)
                responseText = stream->readEntireStreamAsString();
            
            juce::MessageManager::callAsync([callback, success, responseText]()
            {
                juce::var parsedJson;
                if (success)
                    juce::JSON::parse(responseText, parsedJson);
                    
                callback(success, parsedJson);
            });
        });
    }
};
