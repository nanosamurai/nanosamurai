# Parakeet

Parakeet TDT provides refined and final transcripts. It runs by default in two services:

- `parakeet-refinement` processes audio windows during the session.
- `parakeet-finalizer` processes the complete recording after you stop.

Both use Sortformer speaker labels and provide native word timing.
Parakeet does not provide realtime transcription in this stack;
[Nemotron](nemotron.md) provides that by default.

## Model sizes and variants

NVIDIA publishes several Parakeet variants. These TDT models differ in language coverage as well as size:

| Upstream model | Language coverage | Available in this stack |
| --- | --- | --- |
| [TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | Multilingual | Current selection for both workers |
| [TDT 1.1B](https://huggingface.co/nvidia/parakeet-tdt-1.1b) | English | Requires an adapter update and validation |

The current adapter selects `nvidia/parakeet-tdt-0.6b-v3` in Q8 format.
Q8 uses 8-bit weights; it does not reduce the number of model parameters.
The adapter fixes the model file, revision, and checksum.
It has no model-size setting and does not select a size from available GPU memory.
Treat a different Parakeet variant as a separate deployment choice. Check its language and runtime support first.

Parakeet and Sortformer need no Hugging Face token. The first startup downloads them.
Both use the CC BY 4.0 license; see their model cards.
The two workers share a disk cache, but each loads separate weights into GPU memory.

## Languages

Parakeet detects the language of each window or recording.
The session language does not change recognition.
The model card lists 25 European languages, including German. This stack is tested with English.
Check the results with your own audio before you use it for another language.

## Compare Parakeet with another model

With the [Whisper](whisper.md#add-whisper) or [Qwen worker](qwen.md#add-refined-and-final-transcription) overlay,
open **Session settings** and select both models in **Refined**, **Final**, or both.
With no defaults set, Parakeet stays the initial choice because it is listed first.
Keep recording storage enabled when you select two final models.

## Replace Parakeet

To use WhisperX or Qwen instead, follow
[Use Whisper instead of Nemotron and Parakeet](whisper.md#use-whisper-instead-of-nemotron-and-parakeet)
or [Use Qwen instead of Parakeet](qwen.md#use-qwen-instead-of-parakeet).
Both examples set the Parakeet workers to zero replicas and change the API's track lists.
Saved Parakeet transcripts stay available.

## Limits and checks

Parakeet supports up to four anonymous speakers per window or final recording.
It does not match enrolled names. Speaker labels restart in each refinement window.
Equal labels in different windows do not prove that the speaker is the same.

The whole recording is loaded for the final transcript, so long recordings need more memory.

Use [developer smoke tests](../smoke-tests.md#check-the-models) to verify both stages.
See the [Xamurai pipeline guide](https://github.com/nanosamurai/xamurai/blob/master/docs/parakeet-refinement.md)
for worker settings and timing details.
