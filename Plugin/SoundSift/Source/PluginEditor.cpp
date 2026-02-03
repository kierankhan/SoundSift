#include "PluginProcessor.h"
#include "PluginEditor.h"

SoundSiftAudioProcessorEditor::SoundSiftAudioProcessorEditor (SoundSiftAudioProcessor& p)
    : AudioProcessorEditor (&p),
      audioProcessor (p),
      audioPlayer (p)  // <--- CRITICAL FIX: Pass the processor to the player here
{
    // Embed button (now "Index Folder")
    addAndMakeVisible(embedButton);
    embedButton.setButtonText("Index Folder");
    embedButton.onClick = [this] { embedButtonClicked(); };
    
    // Search box
    addAndMakeVisible(searchBox);
    searchBox.setTextToShowWhenEmpty("Enter search query...", juce::Colours::grey);
    searchBox.setMultiLine(false);
    searchBox.setReturnKeyStartsNewLine(false);
    searchBox.onReturnKey = [this] { searchButtonClicked(); };
    
    // Search button
    addAndMakeVisible(searchButton);
    searchButton.setButtonText("Search");
    searchButton.onClick = [this] { searchButtonClicked(); };
    
    // Top K slider
    addAndMakeVisible(topKSlider);
    topKSlider.setRange(1, 50, 1);
    topKSlider.setValue(10);
    topKSlider.setTextBoxStyle(juce::Slider::TextBoxRight, false, 50, 20);
    topKSlider.onValueChange = [this] { topK = (int)topKSlider.getValue(); };
    
    addAndMakeVisible(topKLabel);
    topKLabel.setText("Results:", juce::dontSendNotification);
    topKLabel.attachToComponent(&topKSlider, true);
    
    // Results list
    addAndMakeVisible(resultsList);
    resultsModel = std::make_unique<ResultsListBoxModel>(*this);
    resultsList.setModel(resultsModel.get());
    resultsList.setRowHeight(30);
    
    // Audio player
    addAndMakeVisible(audioPlayer);
    
    // Status label
    addAndMakeVisible(statusLabel);
    statusLabel.setText("Ready - Click 'Index Folder' to begin", juce::dontSendNotification);
    
    // --- REMOVED: audioProcessor.setAudioPlayer(&audioPlayer); ---
    // The player now controls the processor directly via the reference passed in the initializer list.
    
    setSize(600, 550);
}

SoundSiftAudioProcessorEditor::~SoundSiftAudioProcessorEditor()
{
    // --- REMOVED: audioProcessor.setAudioPlayer(nullptr); ---
    // No longer needed.
}

void SoundSiftAudioProcessorEditor::paint (juce::Graphics& g)
{
    g.fillAll(getLookAndFeel().findColour(juce::ResizableWindow::backgroundColourId));
}

void SoundSiftAudioProcessorEditor::resized()
{
    auto area = getLocalBounds().reduced(10);
    
    // Top section: Index button
    embedButton.setBounds(area.removeFromTop(40).reduced(2));
    area.removeFromTop(10);
    
    // Top K slider
    auto sliderArea = area.removeFromTop(30);
    topKSlider.setBounds(sliderArea.reduced(2));
    area.removeFromTop(10);
    
    // Search section
    auto searchArea = area.removeFromTop(40);
    searchButton.setBounds(searchArea.removeFromRight(100).reduced(2));
    searchBox.setBounds(searchArea.reduced(2));
    area.removeFromTop(10);
    
    // Results list
    resultsList.setBounds(area.removeFromTop(200).reduced(2));
    area.removeFromTop(10);
    
    // Audio player
    audioPlayer.setBounds(area.removeFromTop(100).reduced(2));
    area.removeFromTop(10);
    
    // Status label
    statusLabel.setBounds(area.removeFromTop(30).reduced(2));
}

void SoundSiftAudioProcessorEditor::embedButtonClicked()
{
    auto chooserFlags = juce::FileBrowserComponent::openMode
                      | juce::FileBrowserComponent::canSelectDirectories;
    
    fileChooser = std::make_unique<juce::FileChooser>("Select sample folder to index",
                                                       juce::File(),
                                                       "",
                                                       true);
    
    fileChooser->launchAsync(chooserFlags, [this](const juce::FileChooser& fc)
    {
        auto directory = fc.getResult();
        
        if (directory == juce::File())
            return; // User cancelled
        
        juce::String folderPath = directory.getFullPathName();
        
        statusLabel.setText("Indexing folder: " + directory.getFileName() + "...",
                             juce::dontSendNotification);
        
        apiClient.indexFolder(folderPath,
            [this](bool success, juce::var response)
            {
                juce::MessageManager::callAsync([this, success, response]()
                {
                    if (success && response.hasProperty("status"))
                    {
                        auto status = response["status"].toString();
                        if (status == "ok")
                        {
                            int filesEmbedded = response.getProperty("files_embedded", 0);
                            statusLabel.setText("Indexed " + juce::String(filesEmbedded) + " files!",
                                                 juce::dontSendNotification);
                        }
                        else
                        {
                            statusLabel.setText("Indexing failed", juce::dontSendNotification);
                        }
                    }
                    else
                    {
                        statusLabel.setText("Indexing request failed", juce::dontSendNotification);
                    }
                });
            }
        );
    });
}

void SoundSiftAudioProcessorEditor::searchButtonClicked()
{
    auto query = searchBox.getText();
    
    if (query.isEmpty())
    {
        statusLabel.setText("Please enter a search query", juce::dontSendNotification);
        return;
    }
    
    statusLabel.setText("Searching for: " + query + "...", juce::dontSendNotification);
    
    apiClient.queryText(query, topK,
        [this](bool success, juce::var response)
        {
            juce::MessageManager::callAsync([this, success, response]()
            {
                if (success && response.hasProperty("results"))
                {
                    searchResults.clear();
                    auto results = response["results"];
                   
                    if (results.isArray())
                    {
                        auto* array = results.getArray();
                       
                        for (auto& item : *array)
                        {
                            // Your API returns results as objects with 'path' and 'similarity'
                            if (item.isObject() && item.hasProperty("path"))
                            {
                                searchResults.add(item["path"].toString());
                            }
                            // Or if it returns just strings
                            else if (item.isString())
                            {
                                searchResults.add(item.toString());
                            }
                        }
                       
                        resultsList.updateContent();
                        statusLabel.setText("Found " + juce::String(searchResults.size()) + " results",
                                             juce::dontSendNotification);
                    }
                    else
                    {
                        statusLabel.setText("No results found", juce::dontSendNotification);
                    }
                }
                else
                {
                    statusLabel.setText("Search failed - is the index loaded?", juce::dontSendNotification);
                }
            });
        }
    );
}

void SoundSiftAudioProcessorEditor::resultItemClicked(int index)
{
    
    // TODO: Stop current audio
    audioPlayer.changeState(AudioPlayer::TransportState::Stopped);
    if (index >= 0 && index < searchResults.size())
    {
        juce::File audioFile(searchResults[index]);
        
        if (audioFile.existsAsFile())
        {
            // This now calls AudioPlayer::loadFile -> Processor::loadFile
            audioPlayer.loadFile(audioFile);
            statusLabel.setText("Loaded: " + audioFile.getFileName(), juce::dontSendNotification);
        }
        else
        {
            statusLabel.setText("File not found: " + audioFile.getFileName(), juce::dontSendNotification);
        }
    }
}
