"""
Python-specific module: test scene builder server
Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
The scene builder served on standard input and output, as an editor host uses it
===============================================================================
The process is started as a host starts it (``python -m
ray_tracing_shapely.builder.server``) and spoken to in JSON lines:
- ``hello`` gives the page's module and CSS and the package's version;
- a document's text is loaded, edited by pointer messages, and comes back as
  the scene file's text, which reads back as the same scene;
- a half-built object is never in the text; an unreadable document is refused
  and never overwritten; a malformed line is answered with an error and the
  process goes on.
===============================================================================
"""

import json
import subprocess
import sys

import pytest

from ray_tracing_shapely.analysis import scene_file as sf


class _Server:
    def __init__(self):
        self.proc = subprocess.Popen([sys.executable, "-m", "ray_tracing_shapely.builder.server"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)
        self.next = 0

    def raw(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def __call__(self, kind, **fields):
        self.next += 1
        reply = self.raw(json.dumps({"id": self.next, "message": {"type": kind, **fields}}))
        assert reply["id"] == self.next
        return reply["state"]

    def close(self):
        self.proc.stdin.close()
        return self.proc.wait(timeout=20)


@pytest.fixture
def server():
    s = _Server()
    yield s
    assert s.close() == 0


def test_hello_gives_the_page_and_the_version(server):
    hello = server("hello")
    assert "export default { render }" in hello["esm"] and ".rsb" in hello["css"]
    import ray_tracing_shapely
    assert hello["version"] == ray_tracing_shapely.__version__


def test_a_document_is_loaded_edited_and_written_back_as_the_same_scene(server):
    s = server("load_text", text="")
    assert s["host"] == "vscode" and s["error"] is None and s["objects"] == []
    server("tool", name="Mirror")
    s = server("press", x=0, y=0)
    assert s["text"] is None                                  # half-built: nothing to write yet
    s = server("release", x=10, y=0)
    text = s["text"]
    scene = sf.scene_from_dict(json.loads(text))
    assert [o.name for o in scene.objs] == ["Mirror1"]
    s = server("load_text", text=text)                        # reopened from what was written
    assert [o["name"] for o in s["objects"]] == ["Mirror1"] and s["text"] == text


def test_an_unreadable_document_is_refused_and_never_written(server):
    s = server("load_text", text="{not json")
    assert "not a scene the builder can read" in s["error"] and s["text"] is None
    server("tool", name="Mirror")
    s = server("press", x=0, y=0)
    assert "fix its text first" in s["error"] and s["text"] is None


def test_a_malformed_request_is_answered_and_the_server_goes_on(server):
    reply = server.raw("not json")
    assert reply["id"] is None and "JSONDecodeError" in reply["error"]
    assert server("refresh")["error"] is None
